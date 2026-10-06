/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
 * SPDX-License-Identifier: MIT
 *
 * The plugin, loaded the way phosh loads it.
 *
 * Not "does it compile": phosh finds this thing through a GIO extension
 * point, and everything that can go wrong there goes wrong silently - a
 * module that is never scanned, a name that does not match the one in the
 * settings, a type that is not a GtkWidget. The shell says one line,
 * "Custom status-icon '…' not found", and carries on without it.
 *
 * So this does what src/plugin-loader.c does: register the extension point,
 * scan the directory, ask for the extension by the name the settings will
 * hold, build the widget - and then drive it through the file it reads.
 *
 * And it does one thing more, because the widget now has an opinion about
 * where it stands: it builds the shell's shape around it. The plugin looks
 * for an ancestor called PhoshStatusIconsBox and a battery called
 * PhoshBatteryInfo, both by name, because neither type is in any header we
 * have. Nothing in this process has registered those names, so the test
 * registers them itself - a box and a battery that are what the plugin
 * looks for, which is the only part of the shell its placement depends on.
 * How phosh then sorts by priority is phosh's own code, read and measured on
 * the phone, not repeated here.
 */

#include <gtk/gtk.h>
#include <gio/gio.h>
#include <glib/gstdio.h>
#include <dlfcn.h>
#include <phosh-plugin.h>

#define PLUGIN_NAME "furios-battery-time"
/* What phosh gives every status icon, and what the plugin has to end up
   sharing with the battery to stand next to it. */
#define DEFAULT_PRIORITY 10

static int checks = 0;
static int failures = 0;


static void
ok (const char *what)
{
  checks++;
  g_print ("  \033[32mok\033[0m   %s\n", what);
}


static void
fail (const char *what, const char *detail)
{
  checks++;
  failures++;
  g_print ("  \033[31mFAIL\033[0m %s\n       %s\n", what, detail ? detail : "");
}


static void
check_true (const char *what, gboolean value)
{
  if (value)
    ok (what);
  else
    fail (what, "expected true");
}


static void
check_int (const char *what, int have, int want)
{
  if (have == want) {
    ok (what);
  } else {
    g_autofree char *detail = g_strdup_printf ("expected %d, got %d", want, have);
    fail (what, detail);
  }
}


/* The one symbol the plugin borrows from the shell. Here it comes out of the
   shell's library by hand, because a test binary is not phosh: without it
   the module cannot even be loaded, which is a skip and not a failure. */
static GType
load_phosh_status_icon_type (void)
{
  static const char *sonames[] = {
    "libphosh-0.45.so.0", "libphosh-0.46.so.0", "libphosh-0.47.so.0", NULL
  };
  GType (*get_type) (void);
  void *lib = NULL;

  for (int i = 0; sonames[i] && lib == NULL; i++)
    lib = dlopen (sonames[i], RTLD_NOW | RTLD_GLOBAL);

  if (lib == NULL)
    return 0;

  get_type = dlsym (lib, "phosh_status_icon_get_type");
  if (get_type == NULL)
    return 0;

  return get_type ();
}


/* A type of phosh's that this process has no way to build: registered here
   under the shell's name, deriving from what the shell derives it from, so
   the plugin's lookup by name finds the same shape it finds in the bar. */
static GType
stand_in_type (const char *name, GType parent)
{
  GTypeQuery query = { 0 };
  GTypeInfo info = { 0 };

  g_type_query (parent, &query);
  g_return_val_if_fail (query.type != 0, 0);

  info.class_size = query.class_size;
  info.instance_size = query.instance_size;

  return g_type_register_static (parent, name, &info, 0);
}


static void
count_notify (int *count)
{
  (*count)++;
}


static GtkLabel *
label_of (GtkWidget *widget)
{
  GtkWidget *label = NULL;

  g_object_get (widget, "extra_widget", &label, NULL);
  if (label)
    g_object_unref (label);       /* borrowed: the status icon holds it */

  return GTK_IS_LABEL (label) ? GTK_LABEL (label) : NULL;
}


static int
priority_of (gpointer icon)
{
  int priority = -1;

  g_object_get (icon, "priority", &priority, NULL);

  return priority;
}


/* The monitor delivers on the main context, so nothing here can be asserted
   on the next line. Pump it until the label says what it should, or until
   the patience runs out - two seconds is an eternity for inotify and short
   enough that a broken test does not hang a suite. */
static gboolean
settles_to (GtkWidget *widget, const char *want_text, gboolean want_visible)
{
  gint64 deadline = g_get_monotonic_time () + 2 * G_USEC_PER_SEC;
  GtkLabel *label = label_of (widget);

  if (label == NULL)
    return FALSE;

  while (g_get_monotonic_time () < deadline) {
    const char *have = gtk_label_get_text (label);
    gboolean visible = gtk_widget_get_visible (widget);

    if (visible == want_visible && (!want_text || g_strcmp0 (have, want_text) == 0))
      return TRUE;
    g_main_context_iteration (NULL, FALSE);
    g_usleep (10 * 1000);
  }
  return FALSE;
}


static void
write_file (const char *path, const char *text, gsize len)
{
  g_autoptr (GError) error = NULL;

  /* Written beside the target and renamed, which is how battctl writes it:
     the widget must survive the inode changing under its monitor. */
  if (!g_file_set_contents (path, text, len, &error))
    g_error ("could not write %s: %s", path, error->message);
}


/* The first image inside a status icon - the one phosh draws the battery
   with. Borrowed. */
static GtkWidget *
image_of (GtkWidget *icon)
{
  GtkWidget *box = gtk_bin_get_child (GTK_BIN (icon));
  GList *children;
  GtkWidget *image = NULL;

  if (!GTK_IS_CONTAINER (box))
    return NULL;
  children = gtk_container_get_children (GTK_CONTAINER (box));
  for (GList *l = children; l && image == NULL; l = l->next) {
    if (GTK_IS_IMAGE (l->data))
      image = l->data;
  }
  g_list_free (children);

  return image;
}


static void
colour_of (GtkWidget *widget, GdkRGBA *rgba)
{
  GtkStyleContext *context = gtk_widget_get_style_context (widget);

  gtk_style_context_get_color (context, gtk_style_context_get_state (context), rgba);
}


/* Like settles_to, for the colour an image is drawn in. */
static gboolean
colour_settles_to (GtkWidget *image, const GdkRGBA *want)
{
  gint64 deadline = g_get_monotonic_time () + 2 * G_USEC_PER_SEC;

  while (g_get_monotonic_time () < deadline) {
    GdkRGBA have;

    colour_of (image, &have);
    if (gdk_rgba_equal (&have, want))
      return TRUE;
    g_main_context_iteration (NULL, FALSE);
    g_usleep (10 * 1000);
  }
  return FALSE;
}


/*
 * phosh's own rule for the indicator box, as its common.css has it:
 *
 *   phosh-top-panel .indicators { font-size: 13px; font-weight: 800;
 *                                 font-feature-settings: "tnum"; }
 *
 * Applied here to the stand-in box by its style class, because the shell's
 * stylesheet is not loaded in a test process. What is being checked is not
 * that phosh has this rule - it does - but that our label is left to inherit
 * it, instead of carrying a size of its own.
 */
#define INDICATORS_FONT_PX 13.0

static void
apply_indicators_rule (GtkWidget *box)
{
  g_autoptr (GtkCssProvider) provider = gtk_css_provider_new ();

  gtk_css_provider_load_from_data (provider,
                                   ".indicators {"
                                   "  font-size: 13px;"
                                   "  font-weight: 800;"
                                   "  font-feature-settings: \"tnum\";"
                                   "}", -1, NULL);
  gtk_style_context_add_class (gtk_widget_get_style_context (box), "indicators");
  gtk_style_context_add_provider (gtk_widget_get_style_context (box),
                                  GTK_STYLE_PROVIDER (provider),
                                  GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
}


/* The label's weight as GTK will draw it. */
static int
font_weight_of (GtkLabel *label)
{
  GtkStyleContext *context = gtk_widget_get_style_context (GTK_WIDGET (label));
  PangoFontDescription *desc = NULL;
  int weight;

  gtk_style_context_get (context, gtk_style_context_get_state (context),
                         GTK_STYLE_PROPERTY_FONT, &desc, NULL);
  if (desc == NULL)
    return 0;

  weight = pango_font_description_get_weight (desc);
  pango_font_description_free (desc);

  return weight;
}


/* The label's size as GTK will draw it, in pixels. */
static double
font_size_of (GtkLabel *label)
{
  GtkStyleContext *context = gtk_widget_get_style_context (GTK_WIDGET (label));
  PangoFontDescription *desc = NULL;
  double size;

  gtk_style_context_get (context, gtk_style_context_get_state (context),
                         GTK_STYLE_PROPERTY_FONT, &desc, NULL);
  if (desc == NULL)
    return 0;

  size = (double) pango_font_description_get_size (desc) / PANGO_SCALE;
  if (!pango_font_description_get_size_is_absolute (desc))
    size = size * 96.0 / 72.0;  /* points, at GTK's own resolution */
  pango_font_description_free (desc);

  return size;
}


/* The colour at one point of the icon, in 16ths of its size, as GTK draws
   the image - through the draw signal, so the plugin's hand is in it. */
static void
pixel_of (GtkWidget *image, int size, double ux, double uy, GdkRGBA *rgba)
{
  int width = gtk_widget_get_allocated_width (image);
  int height = gtk_widget_get_allocated_height (image);
  cairo_surface_t *surface = cairo_image_surface_create (CAIRO_FORMAT_ARGB32, width, height);
  cairo_t *cr = cairo_create (surface);
  int x = (width - size) / 2 + (int) (ux * size / 16);
  int y = (height - size) / 2 + (int) (uy * size / 16);
  guint32 pixel;
  double alpha;

  gtk_widget_draw (image, cr);
  cairo_destroy (cr);
  cairo_surface_flush (surface);
  pixel = *(guint32 *) (cairo_image_surface_get_data (surface) +
                        y * cairo_image_surface_get_stride (surface) + x * 4);
  cairo_surface_destroy (surface);

  /* Premultiplied: back to the colour itself. */
  alpha = (pixel >> 24) / 255.0;
  rgba->alpha = alpha;
  rgba->red = alpha ? ((pixel >> 16) & 0xff) / 255.0 / alpha : 0;
  rgba->green = alpha ? ((pixel >> 8) & 0xff) / 255.0 / alpha : 0;
  rgba->blue = alpha ? (pixel & 0xff) / 255.0 / alpha : 0;
}


static gboolean
is_reddish (const GdkRGBA *c)
{
  return c->alpha > 0.9 && c->red > 0.8 && c->green < 0.3 && c->blue < 0.3;
}


int
main (int argc, char *argv[])
{
  g_autofree char *runtime_dir = NULL;
  g_autofree char *state = NULL;
  g_autofree char *colour = NULL;
  GtkWidget *battery_image, *other_image;
  GdkRGBA plain, red;
  GIOExtensionPoint *ep;
  GIOExtension *extension;
  GtkWidget *widget, *box, *battery, *other;
  GType status_icon_type, box_type, battery_type;
  GType type;
  double default_font_size;

  if (argc < 2) {
    g_printerr ("usage: %s <directory holding the built plugin>\n", argv[0]);
    return 2;
  }

  /* Before anything else asks GLib where the runtime directory is: it
     answers once and remembers. The plugin reads its file in there, and a
     test that wrote into the real one would be writing into the running
     shell's state. */
  runtime_dir = g_dir_make_tmp ("battery-time-test-XXXXXX", NULL);
  g_setenv ("XDG_RUNTIME_DIR", runtime_dir, TRUE);
  state = g_build_filename (runtime_dir, "furios-battery-time", NULL);
  colour = g_build_filename (runtime_dir, "furios-battery-color", NULL);

  if (!gtk_init_check (&argc, &argv)) {
    g_print ("  \033[33mskipped\033[0m - no display to build a GTK widget on\n");
    return 77;
  }

  status_icon_type = load_phosh_status_icon_type ();
  if (status_icon_type == 0) {
    g_print ("  \033[33mskipped\033[0m - no libphosh to be a status icon in"
             " (apt install libphosh-0.45-0)\n");
    return 77;
  }

  box_type = stand_in_type ("PhoshStatusIconsBox", GTK_TYPE_BOX);
  battery_type = stand_in_type ("PhoshBatteryInfo", status_icon_type);

  /* src/plugin-loader.c, phosh_plugin_loader_constructed(). */
  ep = g_io_extension_point_register (PHOSH_PLUGIN_EXTENSION_POINT_STATUS_ICON_WIDGET);
  g_io_extension_point_set_required_type (ep, GTK_TYPE_WIDGET);
  g_io_modules_scan_all_in_directory (argv[1]);

  extension = g_io_extension_point_get_extension_by_name (ep, PLUGIN_NAME);
  if (extension == NULL) {
    fail ("the shell finds it under the name the settings hold",
          "no extension '" PLUGIN_NAME "' after scanning the directory");
    g_print ("\n\033[31m%d of %d checks failed\033[0m\n", failures, checks);
    return 1;
  }
  ok ("the shell finds it under the name the settings hold");

  type = g_io_extension_get_type (extension);
  check_true ("and what it finds is a widget", g_type_is_a (type, GTK_TYPE_WIDGET));
  check_true ("a status icon, so the bar sorts it with the icons",
              g_type_is_a (type, status_icon_type));

  /* What a label of ours is drawn at when nobody says otherwise. Taken from
     a plain label in this process, so the check below is "we add nothing",
     not "we add exactly this". */
  {
    GtkWidget *plain = gtk_label_new ("x");
    g_object_ref_sink (plain);
    default_font_size = font_size_of (GTK_LABEL (plain));
    g_object_unref (plain);
  }

  /* A time is already there when the widget is built - the ordinary case
     after the shell restarts with the daemon running. */
  write_file (state, "04:38\n", 6);
  widget = g_object_new (type, NULL);
  g_object_ref_sink (widget);
  check_true ("a time that is already there is shown at once",
              settles_to (widget, "04:38", TRUE));
  check_int ("and it asks for a place one below the icons around it",
             priority_of (widget), DEFAULT_PRIORITY - 1);
  check_true ("nothing of its own decides the size - the box does",
              font_size_of (label_of (widget)) == default_font_size);

  /* The bar, as far as the plugin cares about it: a box under the name it
     looks for, a battery in it, and one other icon that must stay where it
     is. */
  box = g_object_new (box_type, NULL);
  g_object_ref_sink (box);
  other = g_object_new (status_icon_type, NULL);
  battery = g_object_new (battery_type, NULL);
  gtk_container_add (GTK_CONTAINER (box), other);
  gtk_container_add (GTK_CONTAINER (box), battery);
  gtk_container_add (GTK_CONTAINER (box), widget);

  write_file (state, "12:00\n", 6);
  check_true ("a new time replaces it", settles_to (widget, "12:00", TRUE));

  /* The size the percentage is drawn at, and the only thing that puts it on
     our label: phosh's rule for the box, inherited by what stands in it. The
     shell's own stylesheet is not in this process, so the rule is applied
     here the way phosh applies it - to the box, by its style class. */
  apply_indicators_rule (box);
  check_true ("in the box it is the size of the percentage beside it",
              font_size_of (label_of (widget)) == INDICATORS_FONT_PX);
  check_true ("and in its weight", font_weight_of (label_of (widget)) >= 700);
  check_int ("the battery comes down to meet it, so the two stand together",
             priority_of (battery), DEFAULT_PRIORITY - 1);
  check_int ("and no other icon is touched",
             priority_of (other), DEFAULT_PRIORITY);

  write_file (state, "", 0);
  check_true ("an empty file shows nothing", settles_to (widget, NULL, FALSE));

  write_file (state, "01:23\n", 6);
  check_true ("and it comes back", settles_to (widget, "01:23", TRUE));

  write_file (state, "0123456789012345678901234567890\n", 32);
  check_true ("a file that is too long is not a label",
              settles_to (widget, NULL, FALSE));

  write_file (state, "02:30\n", 6);
  check_true ("still answering after that", settles_to (widget, "02:30", TRUE));

  write_file (state, "\xff\xfe bad\n", 8);
  check_true ("bytes that are not text show nothing",
              settles_to (widget, NULL, FALSE));

  write_file (state, "03:07\n", 6);
  check_true ("and again after that", settles_to (widget, "03:07", TRUE));

  /* The runtime directory is everybody's: other programs' files come and
     go in it every few seconds, and each one used to make the widget reload
     both of its files inside the shell. The label is scribbled on here so a
     reload shows: a widget that looks at a foreign file puts "03:07" back. */
  {
    g_autofree char *foreign = g_build_filename (runtime_dir, "somebody-else", NULL);
    gint64 until = g_get_monotonic_time () + G_USEC_PER_SEC / 2;

    gtk_label_set_text (label_of (widget), "untouched");
    write_file (foreign, "x\n", 2);
    g_remove (foreign);
    while (g_get_monotonic_time () < until) {
      g_main_context_iteration (NULL, FALSE);
      g_usleep (10 * 1000);
    }
    check_true ("somebody else's file in the directory wakes nothing",
                g_strcmp0 (gtk_label_get_text (label_of (widget)), "untouched") == 0);
    write_file (state, "03:07\n", 6);
    check_true ("but its own file still does", settles_to (widget, "03:07", TRUE));
  }

  g_remove (state);
  check_true ("the file going away takes the time with it",
              settles_to (widget, NULL, FALSE));

  /* The colour. What is checked is the frame, through `color`, because that
     is what GTK will answer about; the palette for the level inside is
     built by the same code from the same line and is looked at on the
     phone. */
  battery_image = image_of (battery);
  other_image = image_of (other);
  check_true ("the battery has an image to colour", battery_image != NULL);
  check_true ("and so does the other icon", other_image != NULL);
  colour_of (battery_image, &plain);
  gdk_rgba_parse (&red, "#e01b24");

  write_file (colour, "frame #e01b24\nfill #2ec27e\n", 27);
  check_true ("the battery takes the colour of the file, with no time shown",
              colour_settles_to (battery_image, &red));
  {
    GdkRGBA have;
    colour_of (other_image, &have);
    check_true ("and no other icon does", gdk_rgba_equal (&have, &plain));
    colour_of (GTK_WIDGET (label_of (widget)), &have);
    check_true ("not even our own label", !gdk_rgba_equal (&have, &red));
  }

  write_file (colour, "frame red; } * { color: red\n", 29);
  check_true ("a line that is not a colour is not CSS - no colour at all",
              colour_settles_to (battery_image, &plain));

  write_file (colour, "frame #e01b24\n", 14);
  check_true ("and the colour comes back", colour_settles_to (battery_image, &red));

  write_file (colour, "fill #2ec27e\n", 13);
  check_true ("the level alone leaves the frame in the bar's own colour",
              colour_settles_to (battery_image, &plain));

  write_file (colour, "frame #e01b24\n", 14);
  colour_settles_to (battery_image, &red);
  g_remove (colour);
  check_true ("the file going away takes the colour with it",
              colour_settles_to (battery_image, &plain));

  write_file (colour, "frame #e01b24\n", 14);
  colour_settles_to (battery_image, &red);

  /* Charging: frame and bolt are one path in Adwaita, and only the bolt
     is to take the colour. Drawn for real, in a window of its own. */
  {
    GtkWidget *window = gtk_offscreen_window_new ();
    GtkWidget *parent = gtk_widget_get_parent (box);
    GdkRGBA bolt, frame, black, around;
    const int size = 32;

    g_assert (parent == NULL);
    gtk_container_add (GTK_CONTAINER (window), box);
    gtk_image_set_from_icon_name (GTK_IMAGE (battery_image),
                                  "battery-level-50-charging-symbolic",
                                  GTK_ICON_SIZE_BUTTON);
    gtk_image_set_pixel_size (GTK_IMAGE (battery_image), size);
    gdk_rgba_parse (&black, "#000000");
    gtk_widget_show_all (window);
    colour_settles_to (battery_image, &black);   /* just pumps: never black */

    /* The bar's own colour is the window's now, so the icon beside it
       says what that is. */
    colour_of (other_image, &around);
    check_true ("charging, the outline is back in the bar's own colour",
                colour_settles_to (battery_image, &around));
    pixel_of (battery_image, size, 10.5, 12.5, &bolt);
    pixel_of (battery_image, size, 2.5, 9.0, &frame);
    check_true ("and the bolt alone takes the colour", is_reddish (&bolt));
    check_true ("the frame beside it does not",
                frame.alpha > 0.9 && !is_reddish (&frame));

    gtk_image_set_from_icon_name (GTK_IMAGE (battery_image),
                                  "battery-level-50-symbolic", GTK_ICON_SIZE_BUTTON);
    check_true ("on battery the frame takes it again",
                colour_settles_to (battery_image, &red));

    g_object_ref (box);
    gtk_container_remove (GTK_CONTAINER (window), box);
    gtk_widget_destroy (window);
  }

  /* Switched off, or the panel torn down: the shell must be left as we
     found it. */
  /* phosh takes an icon out of its box in three steps - find its index,
     unparent it (where we are destroyed), drop that index - and it re-sorts
     the same array whenever a priority changes. A priority changed during
     the destroy therefore drops the wrong icon and leaves a freed one in the
     bar (the crash of 25.9.). So: not one change while it goes. */
  {
    int during = 0;
    gulong id = g_signal_connect_swapped (battery, "notify::priority",
                                          G_CALLBACK (count_notify), &during);

    gtk_widget_destroy (widget);
    check_int ("while it goes, the battery's priority is not touched", during, 0);
    for (int i = 0; i < 50 && priority_of (battery) != DEFAULT_PRIORITY; i++)
      g_main_context_iteration (NULL, FALSE);
    g_signal_handler_disconnect (battery, id);
  }

  /* Destroyed is not finalized: whoever still holds a reference keeps the
     instance - and with it the directory monitor - alive. A time written
     then must not reach it: it would show a widget GTK has already taken
     apart, inside the shell. The reference this test holds stands in for
     the shell's. */
  {
    gint64 until = g_get_monotonic_time () + G_USEC_PER_SEC / 2;

    write_file (state, "05:55\n", 6);
    while (g_get_monotonic_time () < until) {
      g_main_context_iteration (NULL, FALSE);
      g_usleep (10 * 1000);
    }
    check_true ("once destroyed, a new time wakes nothing",
                !gtk_widget_get_visible (widget));
    g_object_unref (widget);
  }
  check_int ("and when it goes, the battery has its priority back",
             priority_of (battery), DEFAULT_PRIORITY);
  {
    GdkRGBA have;
    colour_of (battery_image, &have);
    check_true ("and its own colour", gdk_rgba_equal (&have, &plain));
  }
  g_object_unref (box);

  g_print ("\n");
  if (failures == 0)
    g_print ("\033[32mall %d checks passed\033[0m\n", checks);
  else
    g_print ("\033[31m%d of %d checks failed\033[0m\n", failures, checks);
  return failures > 0 ? 1 : 0;
}
