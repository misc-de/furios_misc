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
 */

#include <gtk/gtk.h>
#include <gio/gio.h>
#include <glib/gstdio.h>
#include <phosh-plugin.h>

#define PLUGIN_NAME "furios-battery-time"

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


/* The monitor delivers on the main context, so nothing here can be asserted
   on the next line. Pump it until the label says what it should, or until
   the patience runs out - two seconds is an eternity for inotify and short
   enough that a broken test does not hang a suite. */
static gboolean
settles_to (GtkWidget *widget, const char *want_text, gboolean want_visible)
{
  gint64 deadline = g_get_monotonic_time () + 2 * G_USEC_PER_SEC;

  while (g_get_monotonic_time () < deadline) {
    const char *have = gtk_label_get_text (GTK_LABEL (widget));
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


int
main (int argc, char *argv[])
{
  g_autofree char *runtime_dir = NULL;
  g_autofree char *state = NULL;
  GIOExtensionPoint *ep;
  GIOExtension *extension;
  GtkWidget *widget;
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

  /* A time is already there when the widget is built - the ordinary case
     after the shell restarts with the daemon running. */
  write_file (state, "04:38\n", 6);
  widget = g_object_new (type, NULL);
  g_object_ref_sink (widget);
  check_true ("a time that is already there is shown at once",
              settles_to (widget, "04:38", TRUE));

  write_file (state, "12:00\n", 6);
  check_true ("a new time replaces it", settles_to (widget, "12:00", TRUE));

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

  g_print ("\n");
  if (failures == 0)
    g_print ("\033[32mall %d checks passed\033[0m\n", checks);
  else
    g_print ("\033[31m%d of %d checks failed\033[0m\n", failures, checks);
  return failures > 0 ? 1 : 0;
}
