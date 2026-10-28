/* Lupin's short-lived, independent WebKitGTK market reader. No game access. */
#include <gtk/gtk.h>
#include <webkit2/webkit2.h>
#include <glib-unix.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>

#define MAX_DOCUMENT (8 * 1024 * 1024)
#define MARKET_URL "https://meso.watch/"
#define READ_DOCUMENT "JSON.stringify(window.MarketData?.doc || null)"
#define SELF_TEST "<!doctype html><meta charset=utf-8><script>" \
    "window.MarketData={doc:{lupinMarketSelfTest:true,text:'한글'}};</script>"

static GtkWidget *window;
static WebKitWebView *view;
static gboolean finished, evaluating;
static int exit_code = 1;

static gboolean quit_loop(gpointer unused) {
    (void)unused;
    gtk_main_quit();
    return G_SOURCE_REMOVE;
}

static void finish(int code, const char *message) {
    if (finished) return;
    finished = TRUE;
    exit_code = code;
    if (message) fprintf(stderr, "%s\n", message);
    webkit_web_view_stop_loading(view);
    gtk_widget_destroy(window);
    g_timeout_add(80, quit_loop, NULL);
}

static void evaluated(GObject *object, GAsyncResult *result, gpointer unused) {
    (void)unused;
    GError *error = NULL;
    JSCValue *value = webkit_web_view_evaluate_javascript_finish(WEBKIT_WEB_VIEW(object), result, &error);
    evaluating = FALSE;
    if (error) { g_error_free(error); return; }
    if (!value) return;
    char *json = jsc_value_to_string(value);
    g_object_unref(value);
    if (!finished && json && strcmp(json, "null")) {
        size_t length = strlen(json);
        if (length > MAX_DOCUMENT || json[0] != '{' || !g_utf8_validate(json, -1, NULL)) {
            finish(12, "The market returned an invalid document.");
        } else if (fwrite(json, 1, length, stdout) != length || fputc('\n', stdout) == EOF || fflush(stdout)) {
            finish(13, "The market document could not be delivered.");
        } else finish(0, NULL);
    }
    g_free(json);
}

static gboolean poll_document(gpointer unused) {
    (void)unused;
    if (finished) return G_SOURCE_REMOVE;
    if (!evaluating) {
        evaluating = TRUE;
        webkit_web_view_evaluate_javascript(view, READ_DOCUMENT, -1, NULL, NULL, NULL, evaluated, NULL);
    }
    return G_SOURCE_CONTINUE;
}

static gboolean timed_out(gpointer unused) {
    (void)unused;
    finish(20, "The market did not become ready before the deadline.");
    return G_SOURCE_REMOVE;
}

static gboolean cancelled(gpointer unused) {
    (void)unused;
    finish(21, NULL);
    return G_SOURCE_REMOVE;
}

static gboolean permission(WebKitWebView *sender, WebKitPermissionRequest *request, gpointer unused) {
    (void)sender; (void)unused;
    webkit_permission_request_deny(request);
    return TRUE;
}

static WebKitWebView *new_window(WebKitWebView *sender, WebKitNavigationAction *action, gpointer unused) {
    (void)sender; (void)action; (void)unused;
    return NULL;
}

int main(int argc, char **argv) {
    gboolean self_test = FALSE;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--self-test")) self_test = TRUE;
        else if (!strcmp(argv[i], "--version")) { puts("Lupin market helper 1 (WebKitGTK)"); return 0; }
        else if (!strcmp(argv[i], "--profile") && i + 1 < argc) i++; /* GTK uses an ephemeral context. */
        else { fputs("Unknown market helper argument.\n", stderr); return 2; }
    }
    (void)setpriority(PRIO_PROCESS, 0, 10);
    if (!gtk_init_check(NULL, NULL)) {
        fputs("A desktop connection is required for the market reader.\n", stderr);
        return 11;
    }
    WebKitWebContext *context = webkit_web_context_new_ephemeral();
    view = WEBKIT_WEB_VIEW(webkit_web_view_new_with_context(context));
    g_object_unref(context);
    WebKitSettings *settings = webkit_web_view_get_settings(view);
    webkit_settings_set_auto_load_images(settings, FALSE);
    webkit_settings_set_hardware_acceleration_policy(settings, WEBKIT_HARDWARE_ACCELERATION_POLICY_NEVER);
    g_signal_connect(view, "permission-request", G_CALLBACK(permission), NULL);
    g_signal_connect(view, "create", G_CALLBACK(new_window), NULL);
    window = gtk_offscreen_window_new();
    gtk_window_set_default_size(GTK_WINDOW(window), 800, 600);
    gtk_container_add(GTK_CONTAINER(window), GTK_WIDGET(view));
    gtk_widget_show_all(window); /* Offscreen container: no visible desktop window. */
    g_unix_signal_add(SIGTERM, cancelled, NULL);
    g_unix_signal_add(SIGINT, cancelled, NULL);
    g_timeout_add(200, poll_document, NULL);
    g_timeout_add_seconds(20, timed_out, NULL);
    if (self_test) webkit_web_view_load_html(view, SELF_TEST, "about:blank");
    else webkit_web_view_load_uri(view, MARKET_URL);
    gtk_main();
    return exit_code;
}
