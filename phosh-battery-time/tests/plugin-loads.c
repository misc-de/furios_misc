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


int
main (int argc, char *argv[])
{
  g_autofree char *runtime_dir = NULL;
  g_autofree char *state = NULL;
  GIOExtensionPoint *ep;
  GIOExtension *extension;
  GtkWidget *widget, *box, *battery, *other;
  GType status_icon_type, box_type, battery_type;
  GType type;

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

  /* A time is already there when the widget is built - the ordinary case
     after the shell restarts with the daemon running. */
  write_file (state, "04:38\n", 6);
  widget = g_object_new (type, NULL);
  g_object_ref_sink (widget);
  check_true ("a time that is already there is shown at once",
              settles_to (widget, "04:38", TRUE));
  check_int ("and it asks for a place one below the icons around it",
             priority_of (widget), DEFAULT_PRIORITY - 1);
  check_true ("in the clock's size, not the box's 13px",
              font_size_of (label_of (widget)) == 16.0);

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

  g_remove (state);
  check_true ("the file going away takes the time with it",
              settles_to (widget, NULL, FALSE));

  /* Switched off, or the panel torn down: the shell must be left as we
     found it. */
  gtk_widget_destroy (widget);
  g_object_unref (widget);
  check_int ("and when it goes, the battery has its priority back",
             priority_of (battery), DEFAULT_PRIORITY);
  g_object_unref (box);

  g_print ("\n");
  if (failures == 0)
    g_print ("\033[32mall %d checks passed\033[0m\n", checks);
  else
    g_print ("\033[31m%d of %d checks failed\033[0m\n", failures, checks);
  return failures > 0 ? 1 : 0;
}
