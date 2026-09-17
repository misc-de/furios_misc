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
 * lock screen included. It also inherits that box's font, which is how it
 * ends up looking like the percentage it replaces without a line of CSS.
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

#define FURIOS_TYPE_BATTERY_TIME (furios_battery_time_get_type ())
G_DECLARE_FINAL_TYPE (FuriosBatteryTime, furios_battery_time,
                      FURIOS, BATTERY_TIME, GtkLabel)

struct _FuriosBatteryTime {
  GtkLabel      parent;
  GFile        *file;
  GFileMonitor *monitor;
};

G_DEFINE_TYPE (FuriosBatteryTime, furios_battery_time, GTK_TYPE_LABEL)


static char *
state_path (void)
{
  const char *run = g_get_user_runtime_dir ();

  /* The runtime directory: it is this user's, it is a tmpfs, and it is
     emptied when the session ends - so a stale time from yesterday cannot
     be sitting there when the shell starts. */
  return g_build_filename (run, "furios-battery-time", NULL);
}


static void
update_label (FuriosBatteryTime *self)
{
  g_autofree char *text = NULL;
  gsize len = 0;

  if (!g_file_load_contents (self->file, NULL, &text, &len, NULL, NULL)) {
    gtk_widget_hide (GTK_WIDGET (self));
    return;
  }
  if (len == 0 || len > MAX_LEN) {
    gtk_widget_hide (GTK_WIDGET (self));
    return;
  }
  g_strstrip (text);
  if (text[0] == '\0' || !g_utf8_validate (text, -1, NULL)) {
    gtk_widget_hide (GTK_WIDGET (self));
    return;
  }
  gtk_label_set_text (GTK_LABEL (self), text);
  gtk_widget_show (GTK_WIDGET (self));
}


static void
on_changed (FuriosBatteryTime *self)
{
  update_label (self);
}


static void
furios_battery_time_finalize (GObject *object)
{
  FuriosBatteryTime *self = FURIOS_BATTERY_TIME (object);

  g_clear_object (&self->monitor);
  g_clear_object (&self->file);

  G_OBJECT_CLASS (furios_battery_time_parent_class)->finalize (object);
}


static void
furios_battery_time_class_init (FuriosBatteryTimeClass *klass)
{
  G_OBJECT_CLASS (klass)->finalize = furios_battery_time_finalize;
}


static void
furios_battery_time_init (FuriosBatteryTime *self)
{
  g_autofree char *path = state_path ();
  g_autoptr (GFile) dir = NULL;

  self->file = g_file_new_for_path (path);

  /* The directory, not the file: battctl writes beside the target and
     renames, so the inode changes on every update and a monitor on the file
     itself would follow the old one into nowhere. */
  dir = g_file_get_parent (self->file);
  self->monitor = g_file_monitor_directory (dir, G_FILE_MONITOR_NONE, NULL, NULL);
  if (self->monitor)
    g_signal_connect_swapped (self->monitor, "changed",
                              G_CALLBACK (on_changed), self);

  /* Nothing to say until there is something to say. phosh shows every
     widget it is handed, so hiding has to be our own doing. */
  gtk_widget_set_no_show_all (GTK_WIDGET (self), TRUE);
  update_label (self);
}


/* --- the GIO module, which is how phosh finds any of this ---------------- */

void
g_io_module_load (GIOModule *module)
{
  /* Pins the module: the type stays valid for as long as phosh runs, which
     is what every other plugin here does. */
  g_type_module_use (G_TYPE_MODULE (module));

  g_io_extension_point_implement (PHOSH_PLUGIN_EXTENSION_POINT_STATUS_ICON_WIDGET,
                                  FURIOS_TYPE_BATTERY_TIME,
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
