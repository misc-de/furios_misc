/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
 * SPDX-License-Identifier: MIT
 *
 * A status icon for phosh's top bar that shows how long the battery has
 * left, written by battctl into one small file.
 *
 * Why a phosh plugin and not a window of our own, which is where this
 * started: a window of ours is a layer surface, phosh's lock screen is a
 * newer one on the same layer, and the newest is on top - so the time was
 * invisible exactly when somebody picks the phone up. A plugin is a widget
 * INSIDE phosh's own indicator box, so it is drawn wherever that box is,
 * lock screen included.
 *
 * Three things follow from being in that box, and all of them cost code:
 *
 *   WHERE it stands. The box sorts status icons by priority and puts
 *   everything else - a plain label, which is what this was - at the very
 *   start, left of every icon. The time then sat a location pin away from
 *   the battery it talks about. So this is a PhoshStatusIcon now, and takes
 *   its place beside the battery by priority (see below).
 *
 *   HOW BIG it is. Nothing here says: the label is left to phosh's own rule
 *   for the box it stands in (`phosh-top-panel .indicators`, 13px, weight
 *   800, tabular figures), which is the rule the percentage beside it is
 *   drawn by. It carried a stylesheet of its own until 17.9.2026, matching
 *   the 16px clock instead - and next to the battery it belongs to, that
 *   read as a second clock rather than as part of the reading.
 *
 *   WHAT COLOUR the battery beside it is. battctl decides the colour and
 *   writes it into a second small file; this widget puts it on the battery
 *   icon's image, through a stylesheet added to that one image's style
 *   context and to nothing else. Until 24.9.2026 battctl did this by
 *   switching the desktop's gtk-theme to generated themes of its own, and
 *   that broke two things it had no business touching: phosh applies the
 *   accent colour only to the themes it knows by name (Adwaita, adw-gtk3
 *   and their -dark forms), so the quick settings fell back to blue, and
 *   Flatpak apps that did not know the name lost their dark mode. Nothing
 *   here reads or writes a setting.
 *
 * This runs in phosh's process. So: it reads two small files, it believes
 * nothing about it, and it does nothing else. Every failure is "show
 * nothing" - a shell that dies because a battery reading was odd would be
 * a far worse bargain than a missing number.
 */

#include <gtk/gtk.h>
#include <gio/gio.h>
#include <phosh-plugin.h>
#include <math.h>
#include <string.h>

/* Long enough for "100:00" and a newline, short enough that a file which is
   not ours cannot become a label. */
#define MAX_LEN 16

/* "frame #rrggbb" and "fill #rrggbb", a line each, and nothing else. */
#define MAX_COLOUR_LEN 64
#define COLOUR_FILE "furios-battery-color"

/* Above the application's own stylesheets, so a rule of phosh's for the
   battery image at the same priority cannot win on specificity alone. It
   only ever reaches the battery's image - see colour_the_battery(). */
#define COLOUR_PRIORITY (GTK_STYLE_PROVIDER_PRIORITY_APPLICATION + 1)

/*
 * The one symbol we borrow from the shell.
 *
 * Declared here rather than included, because phosh-dev ships phosh-plugin.h
 * and nothing else - the rest of the shell's headers are not installed. The
 * declaration is the interface of phosh's own src/status-icon.h
 * (GPL-3.0-or-later, phosh 0.55); nothing of its implementation is copied.
 *
 * It stays undefined in this module and is filled in by the process that
 * loads it. That is not a trick, it is what phosh's own status-icon plugins
 * do - `nm -D libphosh-plugin-simple-custom-status-icon.so` shows the same
 * two undefined phosh_status_icon_* symbols.
 */
GType phosh_status_icon_get_type (void);

/* What phosh gives a status icon that does not ask for anything else, and
   what every icon in the top bar actually has. */
#define PHOSH_DEFAULT_PRIORITY 10

/*
 * Our place: one below the default, shared with the battery.
 *
 * phosh's box keeps its children in descending priority and inserts a new
 * one BEFORE the ones it ties with. So an icon of priority 10 lands left of
 * all of them - left of the location pin, which is not where a battery
 * reading belongs - and one of priority 9 lands right of the lot, past the
 * percentage. Neither is "beside the battery".
 *
 * What is left is to tie with the battery alone: lower it to 9 as well and
 * take 9 ourselves, and the tie puts us immediately in front of it. That is
 * a write into the shell's own widget, so it is small, checked and undone
 * again when this widget goes (see take_place_beside_the_battery). It costs
 * the battery nothing: the box drops icons it cannot fit from the right, and
 * the battery already stood last.
 */
#define OUR_PRIORITY (PHOSH_DEFAULT_PRIORITY - 1)

/* Both looked up by name: their types live in the shell, not in any header
   we have, and a name that phosh renames leaves us where we started rather
   than breaking anything. */
#define ICONS_BOX_TYPE_NAME "PhoshStatusIconsBox"
#define BATTERY_TYPE_NAME   "PhoshBatteryInfo"

/* Everything this widget owns. It hangs off the instance as data rather than
   living in a private struct, because the type is registered at load time
   against whatever size phosh's status icon happens to have - see
   furios_battery_time_get_type(). */
#define DATA_KEY "furios-battery-time"

typedef struct {
  GtkWidget    *self;           /* not a reference: the data lives on it */
  GtkWidget    *label;
  GFile        *file;
  GFile        *colour_file;
  GFileMonitor *monitor;

  /* The colour, and the battery images it is attached to - held, so it can
     be taken off them again when this widget goes. */
  GtkCssProvider *provider;
  GPtrArray      *coloured;

  /* The frame's colour while the battery charges: it goes on the bolt
     alone then, which no stylesheet can reach - see paint_the_bolt(). */
  GdkRGBA         bolt;
  gboolean        has_bolt;

  /* The shell's battery icon, while we have its priority turned down, and
     the value to give back. NULL until we have found it - and after, if
     there is no battery in the bar at all. */
  GObject      *battery;
  int           battery_priority;
  gboolean      placed;
  /* Destroyed: a placement still queued for an idle must not lower the
     battery again after its priority went back. */
  gboolean      gone;
} FuriosBatteryTimeData;


static char *
state_path (const char *name)
{
  const char *run = g_get_user_runtime_dir ();

  /* The runtime directory: it is this user's, it is a tmpfs, and it is
     emptied when the session ends - so a stale time or colour from
     yesterday cannot be sitting there when the shell starts. */
  return g_build_filename (run, name, NULL);
}


static gboolean
has_prop (gpointer object, const char *name)
{
  return g_object_class_find_property (G_OBJECT_GET_CLASS (object), name) != NULL;
}


/* Readable, and an object: GtkContainer has a "child" of its own that is
   write-only and takes a widget by name, so asking every container for one
   would earn a warning from GLib and nothing else. */
static gboolean
can_read_object_prop (gpointer object, const char *name)
{
  GParamSpec *spec = g_object_class_find_property (G_OBJECT_GET_CLASS (object), name);

  return spec != NULL &&
         (spec->flags & G_PARAM_READABLE) &&
         G_TYPE_IS_OBJECT (spec->value_type);
}


static FuriosBatteryTimeData *
get_data (gpointer self)
{
  return g_object_get_data (G_OBJECT (self), DATA_KEY);
}


typedef struct {
  GObject *battery;
  int      priority;
} PriorityBack;


static gboolean
on_idle_priority_back (gpointer user_data)
{
  PriorityBack *back = user_data;

  /* Still in a bar: the box that sorts it is listening, and this is the one
     moment it can safely re-sort. Out of every bar, there is nobody left to
     tell - the next battery the shell builds starts at its own default. */
  if (gtk_widget_get_parent (GTK_WIDGET (back->battery)) != NULL)
    g_object_set (back->battery, "priority", back->priority, NULL);

  return G_SOURCE_REMOVE;
}


static void
priority_back_free (gpointer user_data)
{
  PriorityBack *back = user_data;

  g_object_unref (back->battery);
  g_free (back);
}


/* Give the battery its priority back. The widget is going - because the
   plugin was switched off, or because the shell is tearing the panel down -
   and either way the shell should be left as we found it. On destroy rather
   than on finalize, because somebody else may still hold a reference to a
   widget the shell has already taken out of its bar.
 *
 * NEVER from inside the destroy itself. phosh takes an icon out of its box
 * in three steps: find its index, unparent it (and that is where we are
 * destroyed), then drop that index from its array. A priority changed in
 * between makes the box re-sort that very array, the index points at a
 * different icon, the wrong one is dropped - and the freed one stays in the
 * list for the next walk over the bar to fall on. That was the crash of
 * 25.9. on every change to the status-icons list. So the value goes back
 * from the next idle, when the box has finished. */
static void
give_the_battery_its_priority_back (FuriosBatteryTimeData *data)
{
  PriorityBack *back;

  if (data->battery == NULL)
    return;

  if (has_prop (data->battery, "priority")) {
    back = g_new0 (PriorityBack, 1);
    back->battery = g_object_ref (data->battery);
    back->priority = data->battery_priority;
    g_idle_add_full (G_PRIORITY_DEFAULT, on_idle_priority_back, back,
                     priority_back_free);
  }
  g_clear_object (&data->battery);
}


/* Take our stylesheet off the battery again. Same reasoning as the
   priority: the shell is left as we found it. */
static void
uncolour_the_battery (FuriosBatteryTimeData *data)
{
  if (data->coloured == NULL)
    return;

  for (guint i = 0; i < data->coloured->len; i++) {
    GtkWidget *image = g_ptr_array_index (data->coloured, i);

    gtk_style_context_remove_provider (gtk_widget_get_style_context (image),
                                       GTK_STYLE_PROVIDER (data->provider));
    g_signal_handlers_disconnect_by_data (image, data);
    gtk_widget_queue_draw (image);
  }
  g_ptr_array_set_size (data->coloured, 0);
}


/* The monitor goes with the widget, not with the instance. Somebody may
   hold a reference past the destroy, and until the last one goes the
   monitor would keep calling into a widget GTK has taken apart - its label
   already freed, and gtk_widget_show on what is left. */
static void
stop_watching (FuriosBatteryTimeData *data)
{
  if (data->monitor == NULL)
    return;

  g_signal_handlers_disconnect_by_data (data->monitor, data->self);
  g_file_monitor_cancel (data->monitor);
  g_clear_object (&data->monitor);
}


static void
on_destroy (GtkWidget *self)
{
  FuriosBatteryTimeData *data = get_data (self);

  if (data) {
    data->gone = TRUE;
    stop_watching (data);
    give_the_battery_its_priority_back (data);
    uncolour_the_battery (data);
  }
}


static void
data_free (gpointer user_data)
{
  FuriosBatteryTimeData *data = user_data;

  stop_watching (data);
  give_the_battery_its_priority_back (data);
  uncolour_the_battery (data);
  g_clear_pointer (&data->coloured, g_ptr_array_unref);
  g_clear_object (&data->provider);
  g_clear_object (&data->colour_file);
  g_clear_object (&data->file);
  g_free (data);
}


/* A child of the box is either an icon or a revealer around one. Answer with
   the battery, or NULL for anything else. */
static GObject *
battery_or_null (GtkWidget *child)
{
  GObject *inner = NULL;
  GObject *battery = NULL;

  if (g_strcmp0 (G_OBJECT_TYPE_NAME (child), BATTERY_TYPE_NAME) == 0)
    return G_OBJECT (child);

  if (!can_read_object_prop (child, "child"))
    return NULL;

  g_object_get (child, "child", &inner, NULL);
  if (inner && g_strcmp0 (G_OBJECT_TYPE_NAME (inner), BATTERY_TYPE_NAME) == 0)
    battery = inner;
  /* Borrowed, like the child itself: the revealer holds it for as long as
     it is in the bar, and the caller takes a reference of its own. */
  g_clear_object (&inner);

  return battery;
}


static void
look_at_child (GtkWidget *child, gpointer user_data)
{
  GObject **found = user_data;

  if (*found == NULL)
    *found = battery_or_null (child);
}


/* The images inside a status icon: its bin holds a box, and the box holds
   the image and the extra widget. The caller frees the list, not the
   widgets in it. */
static GList *
images_of (GtkWidget *icon)
{
  GtkWidget *box = GTK_IS_BIN (icon) ? gtk_bin_get_child (GTK_BIN (icon)) : NULL;
  GList *children, *images = NULL;

  if (!GTK_IS_CONTAINER (box))
    return NULL;

  children = gtk_container_get_children (GTK_CONTAINER (box));
  for (GList *l = children; l; l = l->next) {
    if (GTK_IS_IMAGE (l->data))
      images = g_list_prepend (images, l->data);
  }
  g_list_free (children);

  return g_list_reverse (images);
}


/* Our stylesheet on the battery's image, and on nothing else. A provider
   added to one widget's style context reaches that widget alone - not its
   neighbours, not the rest of the shell, not any other program. */
static void on_battery_icon_changed (GtkWidget *image, GParamSpec *pspec,
                                     FuriosBatteryTimeData *data);
static gboolean on_battery_draw (GtkWidget *image, cairo_t *cr,
                                 FuriosBatteryTimeData *data);

static void
colour_the_battery (FuriosBatteryTimeData *data, GObject *battery)
{
  GList *images;

  if (!GTK_IS_WIDGET (battery))
    return;

  images = images_of (GTK_WIDGET (battery));
  for (GList *l = images; l; l = l->next) {
    gtk_style_context_add_provider (gtk_widget_get_style_context (l->data),
                                    GTK_STYLE_PROVIDER (data->provider),
                                    COLOUR_PRIORITY);
    /* Charging or not decides where the frame's colour goes, and phosh
       says which by changing the icon. */
    g_signal_connect (l->data, "notify::icon-name",
                      G_CALLBACK (on_battery_icon_changed), data);
    g_signal_connect (l->data, "notify::gicon",
                      G_CALLBACK (on_battery_icon_changed), data);
    g_signal_connect (l->data, "draw", G_CALLBACK (on_battery_draw), data);
    g_ptr_array_add (data->coloured, g_object_ref (l->data));
  }
  g_list_free (images);
}


/* The icon's name, whichever way phosh handed it over. Borrowed. */
static const char *
icon_name_of (GtkImage *image)
{
  const char *name = NULL;
  GIcon *gicon = NULL;

  switch (gtk_image_get_storage_type (image)) {
  case GTK_IMAGE_ICON_NAME:
    gtk_image_get_icon_name (image, &name, NULL);
    return name;
  case GTK_IMAGE_GICON:
    gtk_image_get_gicon (image, &gicon, NULL);
    if (G_IS_THEMED_ICON (gicon)) {
      const char * const *names = g_themed_icon_get_names (G_THEMED_ICON (gicon));
      return names ? names[0] : NULL;
    }
    return NULL;
  default:
    return NULL;
  }
}


/* battery-level-NN-charging-symbolic: the one family with a bolt. */
static gboolean
is_charging_icon (GtkWidget *image)
{
  const char *name = GTK_IS_IMAGE (image) ? icon_name_of (GTK_IMAGE (image)) : NULL;

  return name != NULL && strstr (name, "-charging") != NULL;
}


static gboolean
any_charging (FuriosBatteryTimeData *data)
{
  for (guint i = 0; data->coloured && i < data->coloured->len; i++) {
    if (is_charging_icon (g_ptr_array_index (data->coloured, i)))
      return TRUE;
  }
  return FALSE;
}


/*
 * Where the bolt is, in Adwaita's 16-unit charging icons - all of them
 * alike, and read out of the SVGs rather than guessed.
 *
 * Frame and bolt are ONE path there, so `color` can only ever take both, and
 * the level inside is a second path whose top edge runs parallel to the
 * bolt's. What keeps them apart is space: the frame stops at y 6 on the
 * right and at x 10 along the bottom, the bolt starts at y 8 and x 9, and
 * the level's diagonal (x + y = 19.2) runs 1.4 units below the bolt's
 * (x + y = 20.6). The outline below goes through the middle of each gap.
 */
static void
bolt_region (cairo_t *cr, double ox, double oy, double unit)
{
  static const double points[][2] = {
    { 12.9, 7.0 }, { 16.5, 7.0 }, { 16.5, 16.5 }, { 10.5, 16.5 },
    { 10.5, 13.6 }, { 9.0, 13.6 }, { 9.0, 10.9 },
  };

  cairo_move_to (cr, ox + points[0][0] * unit, oy + points[0][1] * unit);
  for (guint i = 1; i < G_N_ELEMENTS (points); i++)
    cairo_line_to (cr, ox + points[i][0] * unit, oy + points[i][1] * unit);
  cairo_close_path (cr);
}


/* The box around everything the icon drew, in device pixels. The icon's own
   extremes all sit on whole units - frame top at y 0, frame side at x 2,
   bolt at x 16 and y 16 - so at any size its edges are whole pixels, and
   half coverage is a safe line to draw. */
static gboolean
ink_box (cairo_surface_t *surface, int *x0, int *y0, int *x1, int *y1)
{
  int width = cairo_image_surface_get_width (surface);
  int height = cairo_image_surface_get_height (surface);
  int stride = cairo_image_surface_get_stride (surface);
  const unsigned char *pixels = cairo_image_surface_get_data (surface);

  *x0 = width; *y0 = height; *x1 = -1; *y1 = -1;
  for (int y = 0; y < height; y++) {
    const guint32 *row = (const guint32 *) (pixels + y * stride);

    for (int x = 0; x < width; x++) {
      if ((row[x] >> 24) < 0x80)
        continue;
      *x0 = MIN (*x0, x); *x1 = MAX (*x1, x + 1);
      *y0 = MIN (*y0, y); *y1 = MAX (*y1, y + 1);
    }
  }
  return *x1 > *x0 && *y1 > *y0;
}


/*
 * The icon, drawn by GTK as always, with the bolt in the frame's colour.
 *
 * GTK draws it into a surface of our own first, which also says where it
 * ended up - alignment, size and scale are then GTK's business and not
 * ours to repeat. Everything outside the bolt is copied as it is; inside,
 * the icon's own coverage is used as the mask for the colour, so the bolt
 * keeps its exact shape and edges.
 *
 * Anything that does not look like the icon we measured - another theme,
 * another shape - is drawn as it is, uncoloured.
 */
static gboolean
paint_the_bolt (GtkWidget *image, cairo_t *cr, const GdkRGBA *colour)
{
  int scale = gtk_widget_get_scale_factor (image);
  int width = gtk_widget_get_allocated_width (image);
  int height = gtk_widget_get_allocated_height (image);
  cairo_surface_t *icon;
  cairo_t *icon_cr;
  int x0, y0, x1, y1;
  double unit;

  if (width <= 0 || height <= 0)
    return FALSE;

  icon = cairo_image_surface_create (CAIRO_FORMAT_ARGB32, width * scale, height * scale);
  if (cairo_surface_status (icon) != CAIRO_STATUS_SUCCESS) {
    cairo_surface_destroy (icon);
    return FALSE;
  }
  cairo_surface_set_device_scale (icon, scale, scale);
  icon_cr = cairo_create (icon);
  GTK_WIDGET_GET_CLASS (image)->draw (image, icon_cr);
  cairo_destroy (icon_cr);
  cairo_surface_flush (icon);

  cairo_save (cr);
  if (ink_box (icon, &x0, &y0, &x1, &y1) &&
      (unit = (y1 - y0) / 16.0) > 0 &&
      fabs ((x1 - x0) - 14 * unit) <= 1.0) {
    double ox = (x1 - 16 * unit) / scale;
    double oy = (double) y0 / scale;
    double u = unit / scale;

    cairo_rectangle (cr, 0, 0, width, height);
    bolt_region (cr, ox, oy, u);
    cairo_set_fill_rule (cr, CAIRO_FILL_RULE_EVEN_ODD);
    cairo_clip (cr);
    cairo_set_source_surface (cr, icon, 0, 0);
    cairo_paint (cr);
    cairo_restore (cr);

    cairo_save (cr);
    bolt_region (cr, ox, oy, u);
    cairo_clip (cr);
    gdk_cairo_set_source_rgba (cr, colour);
    cairo_mask_surface (cr, icon, 0, 0);
  } else {
    cairo_set_source_surface (cr, icon, 0, 0);
    cairo_paint (cr);
  }
  cairo_restore (cr);
  cairo_surface_destroy (icon);

  return TRUE;
}


static gboolean
on_battery_draw (GtkWidget *image, cairo_t *cr, FuriosBatteryTimeData *data)
{
  if (!data->has_bolt || !is_charging_icon (image))
    return FALSE;               /* GTK draws it, as it always does */

  return paint_the_bolt (image, cr, &data->bolt);
}


static gboolean
is_hex_colour (const char *text)
{
  if (strlen (text) != 7 || text[0] != '#')
    return FALSE;
  for (int i = 1; i < 7; i++) {
    if (!g_ascii_isxdigit (text[i]))
      return FALSE;
  }
  return TRUE;
}


/*
 * The stylesheet for what the file says, or NULL if it says anything we do
 * not understand. "" is a valid answer: no colour.
 *
 * The file is not taken as CSS. It holds names and colours, and the rule is
 * built here, so nothing written into it can reach further than the two
 * declarations below:
 *
 *   frame   the battery's outline - `color`. While it charges, the bolt
 *           instead and the outline stays plain: Adwaita draws both in one
 *           path, so that half is not CSS at all (see paint_the_bolt) and
 *           comes back through `bolt`.
 *   fill    the level inside, which Adwaita draws with the symbolic
 *           palette: success, and warning/error on the low-level icons
 *
 * A key that is absent is how "no colour" is said for that half.
 */
static char *
colour_css (const char *text, gboolean charging, GdkRGBA *bolt, gboolean *has_bolt)
{
  g_auto (GStrv) lines = g_strsplit (text, "\n", -1);
  g_autoptr (GString) css = g_string_new (NULL);
  const char *frame = NULL, *fill = NULL;
  g_auto (GStrv) words_frame = NULL, words_fill = NULL;

  for (int i = 0; lines[i]; i++) {
    g_auto (GStrv) words = NULL;

    g_strstrip (lines[i]);
    if (lines[i][0] == '\0')
      continue;
    words = g_strsplit (lines[i], " ", -1);
    if (g_strv_length (words) != 2 || !is_hex_colour (words[1]))
      return NULL;
    if (g_str_equal (words[0], "frame") && frame == NULL) {
      words_frame = g_steal_pointer (&words);
      frame = words_frame[1];
    } else if (g_str_equal (words[0], "fill") && fill == NULL) {
      words_fill = g_steal_pointer (&words);
      fill = words_fill[1];
    } else {
      return NULL;
    }
  }

  if (frame && charging) {
    *has_bolt = gdk_rgba_parse (bolt, frame);
    frame = NULL;
  }

  if (frame == NULL && fill == NULL)
    return g_strdup ("");

  g_string_append (css, "image {");
  if (frame)
    g_string_append_printf (css, " color: %s;", frame);
  if (fill)
    g_string_append_printf (css, " -gtk-icon-palette: success %s, warning %s,"
                            " error %s;", fill, fill, fill);
  g_string_append (css, " }");

  return g_string_free (g_steal_pointer (&css), FALSE);
}


/* Read the colour and put it on the stylesheet. Anything odd is "no
   colour": the battery in the bar's own foreground, which is what it was
   before any of this. */
static void
update_colour (GtkWidget *self)
{
  FuriosBatteryTimeData *data = get_data (self);
  g_autofree char *text = NULL;
  g_autofree char *css = NULL;
  gsize len = 0;

  if (data == NULL)
    return;

  data->has_bolt = FALSE;
  if (g_file_load_contents (data->colour_file, NULL, &text, &len, NULL, NULL) &&
      len <= MAX_COLOUR_LEN && g_utf8_validate (text, len, NULL))
    css = colour_css (text, any_charging (data), &data->bolt, &data->has_bolt);
  if (css == NULL)
    data->has_bolt = FALSE;

  gtk_css_provider_load_from_data (data->provider, css ? css : "", -1, NULL);

  /* The bolt is not in the stylesheet, so a change to it alone restyles
     nothing - it has to be asked for. */
  for (guint i = 0; i < data->coloured->len; i++)
    gtk_widget_queue_draw (g_ptr_array_index (data->coloured, i));
}


static void
on_battery_icon_changed (GtkWidget *image, GParamSpec *pspec,
                         FuriosBatteryTimeData *data)
{
  update_colour (data->self);
}


/*
 * Take the place immediately in front of the battery, once, as soon as the
 * shell has put us in its box.
 *
 * Every step can come up empty - a box under another name, no battery, a
 * priority somebody else already moved - and every one of those leaves the
 * widget where phosh put it, which is the right-hand end of the bar. A time
 * in the wrong place is worth far less than a shell we broke rearranging it.
 */
static void
take_place_beside_the_battery (GtkWidget *self)
{
  FuriosBatteryTimeData *data = get_data (self);
  GObject *battery = NULL;
  GtkWidget *box;
  GType box_type;
  int priority = 0;

  if (data == NULL || data->placed || data->gone)
    return;

  box_type = g_type_from_name (ICONS_BOX_TYPE_NAME);
  if (box_type == 0)
    return;

  box = gtk_widget_get_ancestor (self, box_type);
  if (box == NULL)
    return;                     /* not in the bar yet - asked again later */

  /* No battery yet is asked again: the shell may fill its box after it has
     put us in. Found, this is the one attempt there is going to be. */
  gtk_container_foreach (GTK_CONTAINER (box), look_at_child, &battery);
  if (battery == NULL)
    return;
  data->placed = TRUE;

  colour_the_battery (data, battery);
  update_colour (self);

  if (!has_prop (battery, "priority"))
    return;

  g_object_get (battery, "priority", &priority, NULL);
  if (priority <= OUR_PRIORITY)
    return;                     /* already low: leave it alone */

  data->battery = g_object_ref (battery);
  data->battery_priority = priority;
  g_object_set (battery, "priority", OUR_PRIORITY, NULL);

  /* The box sorts on the priority CHANGING, and ours has not - it has been
     OUR_PRIORITY since this widget was built, from before the battery shared
     it. So say it twice, and the second one lands us in the tie. */
  if (has_prop (self, "priority")) {
    g_object_set (self, "priority", OUR_PRIORITY + 1, NULL);
    g_object_set (self, "priority", OUR_PRIORITY, NULL);
  }
}


static void
update_label (GtkWidget *self)
{
  FuriosBatteryTimeData *data = get_data (self);
  g_autofree char *text = NULL;
  gsize len = 0;

  if (data == NULL)
    return;

  if (!g_file_load_contents (data->file, NULL, &text, &len, NULL, NULL)) {
    gtk_widget_hide (self);
    return;
  }
  if (len == 0 || len > MAX_LEN) {
    gtk_widget_hide (self);
    return;
  }
  g_strstrip (text);
  if (text[0] == '\0' || !g_utf8_validate (text, -1, NULL)) {
    gtk_widget_hide (self);
    return;
  }
  gtk_label_set_text (GTK_LABEL (data->label), text);
  take_place_beside_the_battery (self);
  gtk_widget_show (self);
}


/*
 * The monitor watches the whole runtime directory, and that directory is
 * busy: sockets, locks and the temporary files of other programs come and go
 * in it every few seconds (measured on 26.9.2026: well over a dozen foreign
 * names a minute). Each of them used to reload both files, re-parse the
 * stylesheet and redraw the battery, inside the shell's process. So only our
 * two names count, and each only for its own half. The ".new" files battctl
 * renames from do not count either: the rename arrives under the target's
 * name.
 */
static void
on_changed (GtkWidget         *self,
            GFile             *file,
            GFile             *other_file,
            GFileMonitorEvent  event,
            GFileMonitor      *monitor)
{
  FuriosBatteryTimeData *data = get_data (self);

  if (data == NULL || data->gone || file == NULL)
    return;

  if (g_file_equal (file, data->file))
    update_label (self);
  else if (g_file_equal (file, data->colour_file))
    update_colour (self);
  else
    return;

  take_place_beside_the_battery (self);
}


/* The shell puts us into its box after building us. That is the moment the
   battery beside us can be found - whether or not there is a time to show,
   because the colour needs it just as much. */
static gboolean
on_idle_take_place (gpointer self)
{
  take_place_beside_the_battery (self);

  return G_SOURCE_REMOVE;
}


/* Not from here directly: this fires from inside the box's own
   gtk_widget_set_parent, before it has hooked up the icon it is adding, and
   a priority changed in the middle of that is changed under its feet (see
   give_the_battery_its_priority_back). The next idle is soon enough. */
static void
on_hierarchy_changed (GtkWidget *self, GtkWidget *previous_toplevel)
{
  FuriosBatteryTimeData *data = get_data (self);

  if (data && !data->placed)
    g_idle_add_full (G_PRIORITY_DEFAULT_IDLE, on_idle_take_place,
                     g_object_ref (self), g_object_unref);
}


/* The image phosh's status icon brings along. We have no icon to put in it -
   the battery's own is right beside us - and an empty one that is still
   visible would push our text over by the box's spacing. */
static void
hide_the_icon (GtkWidget *self)
{
  GtkWidget *box = gtk_bin_get_child (GTK_BIN (self));
  GList *children;

  if (!GTK_IS_CONTAINER (box))
    return;

  children = gtk_container_get_children (GTK_CONTAINER (box));
  for (GList *l = children; l; l = l->next) {
    if (GTK_IS_IMAGE (l->data)) {
      gtk_widget_set_no_show_all (l->data, TRUE);
      gtk_widget_hide (l->data);
    }
  }
  g_list_free (children);
}


static void
furios_battery_time_init (GTypeInstance *instance, gpointer klass)
{
  GtkWidget *self = GTK_WIDGET (instance);
  FuriosBatteryTimeData *data = g_new0 (FuriosBatteryTimeData, 1);
  g_autofree char *path = state_path ("furios-battery-time");
  g_autofree char *colour_path = state_path (COLOUR_FILE);
  g_autoptr (GFile) dir = NULL;

  data->self = self;
  g_object_set_data_full (G_OBJECT (self), DATA_KEY, data, data_free);

  data->label = gtk_label_new (NULL);
  gtk_widget_set_valign (data->label, GTK_ALIGN_CENTER);
  gtk_widget_show (data->label);

  /* No stylesheet of our own: size, weight and tabular figures are what the
     box gives its children, and that is what the percentage is drawn with.
     Font properties are inherited in CSS, so standing in the box is the
     whole of it. */

  /* The text goes where the percentage goes in phosh's own battery icon:
     the status icon's extra widget, beside the (hidden) image. */
  if (has_prop (self, "extra_widget"))
    g_object_set (self, "extra_widget", data->label, NULL);
  if (has_prop (self, "priority"))
    g_object_set (self, "priority", OUR_PRIORITY, NULL);
  hide_the_icon (self);

  data->file = g_file_new_for_path (path);
  data->colour_file = g_file_new_for_path (colour_path);
  data->provider = gtk_css_provider_new ();
  data->coloured = g_ptr_array_new_with_free_func (g_object_unref);

  /* The directory, not the file: battctl writes beside the target and
     renames, so the inode changes on every update and a monitor on the file
     itself would follow the old one into nowhere. */
  dir = g_file_get_parent (data->file);
  data->monitor = g_file_monitor_directory (dir, G_FILE_MONITOR_NONE, NULL, NULL);
  if (data->monitor)
    g_signal_connect_swapped (data->monitor, "changed",
                              G_CALLBACK (on_changed), self);

  g_signal_connect (self, "destroy", G_CALLBACK (on_destroy), NULL);
  g_signal_connect (self, "hierarchy-changed",
                    G_CALLBACK (on_hierarchy_changed), NULL);

  /* Nothing to say until there is something to say. phosh shows every
     widget it is handed, so hiding has to be our own doing. */
  gtk_widget_set_no_show_all (self, TRUE);
  update_label (self);
  update_colour (self);

  /* We are built before the shell puts us in its box, so the place beside
     the battery cannot be taken yet. The first idle after that is late
     enough, and update_label tries again anyway. */
  g_idle_add_full (G_PRIORITY_DEFAULT_IDLE, on_idle_take_place,
                   g_object_ref (self), g_object_unref);
}


/*
 * The type, registered against phosh's status icon as the shell has it.
 *
 * Not G_DEFINE_TYPE: that needs the parent's struct at compile time, and the
 * only phosh header on the system is the one with the extension point names
 * in it. g_type_query asks the running shell for the two sizes instead, so a
 * phosh that grows a field is a phosh this still loads into.
 */
static GType
furios_battery_time_get_type (void)
{
  static GType type = 0;

  if (g_once_init_enter (&type)) {
    GType parent = phosh_status_icon_get_type ();
    GTypeQuery query = { 0 };
    GTypeInfo info = { 0 };
    GType registered = 0;

    g_type_query (parent, &query);
    if (query.type == 0) {
      /* No shell to be a status icon in. Nothing good can come of guessing
         at the sizes, so this is where we stop - the shell logs the plugin
         as not found and carries on without it. */
      g_warning ("phosh's status icon type is not registered - no battery time");
    } else {
      info.class_size = query.class_size;
      info.instance_size = query.instance_size;
      info.instance_init = furios_battery_time_init;
      registered = g_type_register_static (parent, "FuriosBatteryTime", &info, 0);
    }
    g_once_init_leave (&type, registered);
  }

  return type;
}


/* --- the GIO module, which is how phosh finds any of this ---------------- */

void
g_io_module_load (GIOModule *module)
{
  /* Pins the module: the type stays valid for as long as phosh runs, which
     is what every other plugin here does. */
  g_type_module_use (G_TYPE_MODULE (module));

  g_io_extension_point_implement (PHOSH_PLUGIN_EXTENSION_POINT_STATUS_ICON_WIDGET,
                                  furios_battery_time_get_type (),
                                  "furios-battery-time",
                                  10);
}


void
g_io_module_unload (GIOModule *module)
{
}


char **
g_io_module_query (void)
{
  char *points[] = { (char *) PHOSH_PLUGIN_EXTENSION_POINT_STATUS_ICON_WIDGET,
                     NULL };

  return g_strdupv (points);
}
