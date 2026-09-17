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
 * Two things follow from being in that box, and both cost code:
 *
 *   WHERE it stands. The box sorts status icons by priority and puts
 *   everything else - a plain label, which is what this was - at the very
 *   start, left of every icon. The time then sat a location pin away from
 *   the battery it talks about. So this is a PhoshStatusIcon now, and takes
 *   its place beside the battery by priority (see below).
 *
 *   HOW BIG it is. The box's font is 13px, the size of the percentage. The
 *   clock is 16px, and that is the size this is asked to match, so the label
 *   carries a stylesheet of its own - three declarations, on this one widget
 *   and nothing else.
 *
 * This runs in phosh's process. So: it reads one small file, it believes
 * nothing about it, and it does nothing else. Every failure is "show
 * nothing" - a shell that dies because a battery reading was odd would be
 * a far worse bargain than a missing number.
 */

#include <gtk/gtk.h>
#include <gio/gio.h>
#include <phosh-plugin.h>

/* Long enough for "100:00" and a newline, short enough that a file which is
   not ours cannot become a label. */
#define MAX_LEN 16

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

/* The clock's three declarations, on our label alone. A provider added to
   one widget's style context reaches that widget and nothing else, which is
   why this does not need - and must not have - a screen-wide stylesheet. */
#define LABEL_CSS                            \
  "label {"                                  \
  "  font-size: 16px;"                       \
  "  font-weight: bold;"                     \
  "  font-feature-settings: \"tnum\";"       \
  "}"

/* Everything this widget owns. It hangs off the instance as data rather than
   living in a private struct, because the type is registered at load time
   against whatever size phosh's status icon happens to have - see
   furios_battery_time_get_type(). */
#define DATA_KEY "furios-battery-time"

typedef struct {
  GtkWidget    *label;
  GFile        *file;
  GFileMonitor *monitor;

  /* The shell's battery icon, while we have its priority turned down, and
     the value to give back. NULL until we have found it - and after, if
     there is no battery in the bar at all. */
  GObject      *battery;
  int           battery_priority;
  gboolean      placed;
} FuriosBatteryTimeData;


static char *
state_path (void)
{
  const char *run = g_get_user_runtime_dir ();

  /* The runtime directory: it is this user's, it is a tmpfs, and it is
     emptied when the session ends - so a stale time from yesterday cannot
     be sitting there when the shell starts. */
  return g_build_filename (run, "furios-battery-time", NULL);
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


/* Give the battery its priority back. The widget is going - because the
   plugin was switched off, or because the shell is tearing the panel down -
   and either way the shell should be left as we found it. On destroy rather
   than on finalize, because somebody else may still hold a reference to a
   widget the shell has already taken out of its bar. */
static void
give_the_battery_its_priority_back (FuriosBatteryTimeData *data)
{
  if (data->battery) {
    if (has_prop (data->battery, "priority"))
      g_object_set (data->battery, "priority", data->battery_priority, NULL);
    g_clear_object (&data->battery);
  }
}


static void
on_destroy (GtkWidget *self)
{
  FuriosBatteryTimeData *data = get_data (self);

  if (data)
    give_the_battery_its_priority_back (data);
}


static void
data_free (gpointer user_data)
{
  FuriosBatteryTimeData *data = user_data;

  give_the_battery_its_priority_back (data);
  g_clear_object (&data->monitor);
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

  if (data == NULL || data->placed)
    return;

  box_type = g_type_from_name (ICONS_BOX_TYPE_NAME);
  if (box_type == 0)
    return;

  box = gtk_widget_get_ancestor (self, box_type);
  if (box == NULL)
    return;                     /* not in the bar yet - asked again later */

  /* In the box, so this is the one attempt there is going to be. */
  data->placed = TRUE;

  gtk_container_foreach (GTK_CONTAINER (box), look_at_child, &battery);
  if (battery == NULL || !has_prop (battery, "priority"))
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


static void
on_changed (GtkWidget *self)
{
  update_label (self);
}


static gboolean
on_idle_take_place (gpointer self)
{
  take_place_beside_the_battery (self);

  return G_SOURCE_REMOVE;
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
  g_autoptr (GtkCssProvider) provider = gtk_css_provider_new ();
  g_autofree char *path = state_path ();
  g_autoptr (GFile) dir = NULL;

  g_object_set_data_full (G_OBJECT (self), DATA_KEY, data, data_free);

  data->label = gtk_label_new (NULL);
  gtk_widget_set_valign (data->label, GTK_ALIGN_CENTER);
  gtk_widget_show (data->label);

  gtk_css_provider_load_from_data (provider, LABEL_CSS, -1, NULL);
  gtk_style_context_add_provider (gtk_widget_get_style_context (data->label),
                                  GTK_STYLE_PROVIDER (provider),
                                  GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);

  /* The text goes where the percentage goes in phosh's own battery icon:
     the status icon's extra widget, beside the (hidden) image. */
  if (has_prop (self, "extra_widget"))
    g_object_set (self, "extra_widget", data->label, NULL);
  if (has_prop (self, "priority"))
    g_object_set (self, "priority", OUR_PRIORITY, NULL);
  hide_the_icon (self);

  data->file = g_file_new_for_path (path);

  /* The directory, not the file: battctl writes beside the target and
     renames, so the inode changes on every update and a monitor on the file
     itself would follow the old one into nowhere. */
  dir = g_file_get_parent (data->file);
  data->monitor = g_file_monitor_directory (dir, G_FILE_MONITOR_NONE, NULL, NULL);
  if (data->monitor)
    g_signal_connect_swapped (data->monitor, "changed",
                              G_CALLBACK (on_changed), self);

  g_signal_connect (self, "destroy", G_CALLBACK (on_destroy), NULL);

  /* Nothing to say until there is something to say. phosh shows every
     widget it is handed, so hiding has to be our own doing. */
  gtk_widget_set_no_show_all (self, TRUE);
  update_label (self);

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
