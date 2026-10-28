// Lupin's independent, short-lived WebView2 reader. Every HWND belongs to this helper.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <objbase.h>
#include <shellapi.h>
#ifdef __MINGW32__
// Preserve Microsoft SDK interface UUID attributes with clang's native support.
#undef __uuidof
#undef MIDL_INTERFACE
#define MIDL_INTERFACE(id) struct __declspec(uuid(id))
#endif
#include <wrl/client.h>
#include <functional>
#include <string>
#include <cwchar>
#include <cstdio>
#include "WebView2.h"

using Microsoft::WRL::ComPtr;
constexpr size_t MAX_DOCUMENT = 8 * 1024 * 1024;
constexpr UINT FINISH_MESSAGE = WM_APP + 1;
constexpr wchar_t MARKET_URL[] = L"https://meso.watch/";
constexpr wchar_t READ_DOCUMENT[] =
    L"(()=>{const d=window.MarketData?.doc;if(d)chrome.webview.postMessage(JSON.stringify(d));})()";
constexpr wchar_t SELF_TEST[] = L"<!doctype html><meta charset=utf-8><script>"
    L"window.MarketData={doc:{lupinMarketSelfTest:true,text:'\uD55C\uAE00'}};</script>";

static bool write_pipe(DWORD kind, const std::string &text) {
    HANDLE pipe = GetStdHandle(kind);
    if (!pipe || pipe == INVALID_HANDLE_VALUE) return false;
    size_t offset = 0;
    while (offset < text.size()) {
        DWORD written = 0;
        if (!WriteFile(pipe, text.data() + offset, static_cast<DWORD>(text.size() - offset), &written, nullptr) || !written)
            return false;
        offset += written;
    }
    return true;
}

static std::string utf8(const wchar_t *text) {
    size_t length = wcslen(text);
    if (length > MAX_DOCUMENT) return {};
    int bytes = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, static_cast<int>(length), nullptr, 0, nullptr, nullptr);
    if (bytes <= 0 || static_cast<size_t>(bytes) > MAX_DOCUMENT) return {};
    std::string result(bytes, '\0');
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, static_cast<int>(length), result.data(), bytes, nullptr, nullptr))
        return {};
    return result;
}

// The only process handle used here is obtained from Lupin's own named-pipe
// control server. Waiting for that process also waits for its DLLs to unload.
static int close_panel() {
    wchar_t user[32768];DWORD length=0;
    for (const wchar_t *name : {L"LOGNAME",L"USER",L"LNAME",L"USERNAME"}) {
        length=GetEnvironmentVariableW(name,user,32768);
        if (length && length<32768) break;
    }
    if (!length || length>=32768) return 30;
    std::wstring identity(user,length);
    for (auto &c : identity) if (!((c>=L'a'&&c<=L'z')||(c>=L'A'&&c<=L'Z')||(c>=L'0'&&c<=L'9')||c==L'_')) c=L'_';
    std::wstring name=L"\\\\.\\pipe\\ClassicPriceLens-control-v1-"+identity;
    HANDLE pipe=CreateFileW(name.c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_EXISTING,FILE_FLAG_OVERLAPPED,nullptr);
    if (pipe==INVALID_HANDLE_VALUE) return GetLastError()==ERROR_FILE_NOT_FOUND ? 0 : 30;
    ULONG pid=0;
    if (!GetNamedPipeServerProcessId(pipe,&pid)) { CloseHandle(pipe);return 30; }
    HANDLE process=OpenProcess(SYNCHRONIZE,FALSE,pid);
    if (!process) { CloseHandle(pipe);return 30; }
    HANDLE event=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    bool ok=event!=nullptr;
    auto transfer=[&](bool writing,char *data,DWORD length,DWORD &count) {
        OVERLAPPED operation={};operation.hEvent=event;ResetEvent(event);
        BOOL done=writing ? WriteFile(pipe,data,length,&count,&operation) : ReadFile(pipe,data,length,&count,&operation);
        if (!done && GetLastError()==ERROR_IO_PENDING) {
            if (WaitForSingleObject(event,3000)==WAIT_OBJECT_0) return GetOverlappedResult(pipe,&operation,&count,FALSE)!=FALSE;
            CancelIoEx(pipe,&operation);GetOverlappedResult(pipe,&operation,&count,TRUE);return false;
        }
        return done!=FALSE;
    };
    char request[]="quit\n",reply[32]={};DWORD count=0;
    if (ok) ok=transfer(true,request,5,count) && count==5;
    if (ok) ok=transfer(false,reply,sizeof(reply),count) && count==3 && !memcmp(reply,"ok\n",3);
    if (ok) ok=WaitForSingleObject(process,15000)==WAIT_OBJECT_0;
    if (event) CloseHandle(event);
    CloseHandle(process);CloseHandle(pipe);return ok ? 0 : 30;
}

template<class Interface, class... Args> class Handler final : public Interface {
    LONG references = 1;
    std::function<HRESULT(Args...)> callback;
public:
    explicit Handler(std::function<HRESULT(Args...)> fn) : callback(std::move(fn)) {}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id, void **out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (id != IID_IUnknown && id != __uuidof(Interface)) return E_NOINTERFACE;
        *out = static_cast<Interface *>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&references); }
    ULONG STDMETHODCALLTYPE Release() override { LONG count=InterlockedDecrement(&references); if (!count) delete this; return count; }
    HRESULT STDMETHODCALLTYPE Invoke(Args... args) override { return callback(args...); }
};

template<class Interface, class... Args, class Fn> static ComPtr<Interface> handler(Fn fn) {
    ComPtr<Interface> result;
    result.Attach(new Handler<Interface, Args...>(std::move(fn)));
    return result;
}

// Restrict discovery to the shared production runtime, rather than Edge preview browsers.
class Options final : public ICoreWebView2EnvironmentOptions, public ICoreWebView2EnvironmentOptions7 {
    LONG references = 1;
    std::wstring arguments, language, target = L"124.0.0.0";
    BOOL sign_on = FALSE;
    COREWEBVIEW2_CHANNEL_SEARCH_KIND search = COREWEBVIEW2_CHANNEL_SEARCH_KIND_MOST_STABLE;
    COREWEBVIEW2_RELEASE_CHANNELS channels = COREWEBVIEW2_RELEASE_CHANNELS_STABLE;
    static HRESULT copy(const std::wstring &value, LPWSTR *out) {
        if (!out) return E_POINTER;
        if (value.empty()) { *out=nullptr;return S_OK; }
        *out=static_cast<LPWSTR>(CoTaskMemAlloc((value.size()+1)*sizeof(wchar_t)));
        if (!*out) return E_OUTOFMEMORY;
        memcpy(*out,value.c_str(),(value.size()+1)*sizeof(wchar_t)); return S_OK;
    }
public:
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id, void **out) override {
        if (!out) return E_POINTER;
        *out=nullptr;
        if (id==IID_IUnknown || id==__uuidof(ICoreWebView2EnvironmentOptions)) *out=static_cast<ICoreWebView2EnvironmentOptions *>(this);
        else if (id==__uuidof(ICoreWebView2EnvironmentOptions7)) *out=static_cast<ICoreWebView2EnvironmentOptions7 *>(this);
        else return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&references); }
    ULONG STDMETHODCALLTYPE Release() override { LONG count=InterlockedDecrement(&references); if (!count) delete this; return count; }
    HRESULT STDMETHODCALLTYPE get_AdditionalBrowserArguments(LPWSTR *out) override { return copy(arguments,out); }
    HRESULT STDMETHODCALLTYPE put_AdditionalBrowserArguments(LPCWSTR value) override { arguments=value?value:L""; return S_OK; }
    HRESULT STDMETHODCALLTYPE get_Language(LPWSTR *out) override { return copy(language,out); }
    HRESULT STDMETHODCALLTYPE put_Language(LPCWSTR value) override { language=value?value:L""; return S_OK; }
    HRESULT STDMETHODCALLTYPE get_TargetCompatibleBrowserVersion(LPWSTR *out) override { return copy(target,out); }
    HRESULT STDMETHODCALLTYPE put_TargetCompatibleBrowserVersion(LPCWSTR value) override { target=value?value:L""; return S_OK; }
    HRESULT STDMETHODCALLTYPE get_AllowSingleSignOnUsingOSPrimaryAccount(BOOL *out) override { if (!out)return E_POINTER; *out=sign_on; return S_OK; }
    HRESULT STDMETHODCALLTYPE put_AllowSingleSignOnUsingOSPrimaryAccount(BOOL value) override { sign_on=value; return S_OK; }
    HRESULT STDMETHODCALLTYPE get_ChannelSearchKind(COREWEBVIEW2_CHANNEL_SEARCH_KIND *out) override { if (!out)return E_POINTER; *out=search; return S_OK; }
    HRESULT STDMETHODCALLTYPE put_ChannelSearchKind(COREWEBVIEW2_CHANNEL_SEARCH_KIND value) override { search=value; return S_OK; }
    HRESULT STDMETHODCALLTYPE get_ReleaseChannels(COREWEBVIEW2_RELEASE_CHANNELS *out) override { if (!out)return E_POINTER; *out=channels; return S_OK; }
    HRESULT STDMETHODCALLTYPE put_ReleaseChannels(COREWEBVIEW2_RELEASE_CHANNELS value) override { channels=value; return S_OK; }
};

class MarketReader {
    HWND window = nullptr;
    bool finished = false, self_test, diagnostics;
    int exit_code = 1;
    ULONGLONG started = GetTickCount64();
    ComPtr<ICoreWebView2Environment> environment;
    ComPtr<ICoreWebView2Controller> controller;
    ComPtr<ICoreWebView2> web;
public:
    explicit MarketReader(bool test, bool diagnose) : self_test(test), diagnostics(test || diagnose) {}
    void diagnostic(const char *stage, HRESULT status = S_OK) {
        if (!diagnostics) return;
        char message[160];
        snprintf(message,sizeof(message),"Market helper: %s (0x%08lX)\n",stage,static_cast<unsigned long>(status));
        write_pipe(STD_ERROR_HANDLE,message);
    }
    static LRESULT CALLBACK messages(HWND hwnd, UINT message, WPARAM w, LPARAM l) {
        if (message==WM_NCCREATE) SetWindowLongPtrW(hwnd,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(reinterpret_cast<CREATESTRUCTW *>(l)->lpCreateParams));
        auto *reader=reinterpret_cast<MarketReader *>(GetWindowLongPtrW(hwnd,GWLP_USERDATA));
        if (reader) {
            if (message==WM_TIMER) { reader->poll(); return 0; }
            if (message==WM_CLOSE) { reader->finish(21,nullptr); return 0; }
            if (message==FINISH_MESSAGE) {
                KillTimer(hwnd,1);
                if (reader->controller) reader->controller->Close();
                reader->web.Reset();reader->controller.Reset();reader->environment.Reset();
                DestroyWindow(hwnd);PostQuitMessage(reader->exit_code);return 0;
            }
        }
        return DefWindowProcW(hwnd,message,w,l);
    }
    void finish(int code, const char *error) {
        if (finished) return;
        finished=true;exit_code=code;
        if (error) write_pipe(STD_ERROR_HANDLE,std::string(error)+"\n");
        PostMessageW(window,FINISH_MESSAGE,0,0);
    }
    void poll() {
        if (finished) return;
        if (GetTickCount64()-started>20000) { finish(20,"The market did not become ready before the deadline."); return; }
        if (web) web->ExecuteScript(READ_DOCUMENT,nullptr);
    }
    HRESULT created_controller(HRESULT status, ICoreWebView2Controller *value) {
        diagnostic("controller",status);
        if (finished) return S_OK;
        if (FAILED(status) || !value) { finish(12,"The market reader could not initialize its view."); return S_OK; }
        controller=value;
        RECT bounds={0,0,800,600};controller->put_Bounds(bounds);controller->put_IsVisible(FALSE);
        if (FAILED(controller->get_CoreWebView2(&web))) { finish(12,"The market reader could not initialize its page."); return S_OK; }
        ComPtr<ICoreWebView2Settings> settings;web->get_Settings(&settings);
        if (settings) {
            settings->put_AreDefaultScriptDialogsEnabled(FALSE);settings->put_AreDevToolsEnabled(FALSE);
            settings->put_AreDefaultContextMenusEnabled(FALSE);settings->put_IsStatusBarEnabled(FALSE);
            settings->put_IsWebMessageEnabled(TRUE);
        }
        EventRegistrationToken token;
        auto ready=handler<ICoreWebView2WebMessageReceivedEventHandler,ICoreWebView2 *,ICoreWebView2WebMessageReceivedEventArgs *>(
            [this](ICoreWebView2 *,ICoreWebView2WebMessageReceivedEventArgs *args) {
                if (finished) return S_OK;
                LPWSTR origin=nullptr;args->get_Source(&origin);
                bool trusted=origin && (self_test ? !wcscmp(origin,L"about:blank") : !wcsncmp(origin,MARKET_URL,wcslen(MARKET_URL)));
                CoTaskMemFree(origin);if (!trusted) return S_OK;
                LPWSTR text=nullptr;
                if (SUCCEEDED(args->TryGetWebMessageAsString(&text)) && text) {
                    std::string json=utf8(text);CoTaskMemFree(text);
                    if (json.empty() || json.front()!='{') finish(12,"The market returned an invalid document.");
                    else if (!write_pipe(STD_OUTPUT_HANDLE,json+"\n")) finish(13,"The market document could not be delivered.");
                    else finish(0,nullptr);
                }
                return S_OK;
            });
        web->add_WebMessageReceived(ready.Get(),&token);
        auto permission=handler<ICoreWebView2PermissionRequestedEventHandler,ICoreWebView2 *,ICoreWebView2PermissionRequestedEventArgs *>(
            [](ICoreWebView2 *,ICoreWebView2PermissionRequestedEventArgs *args) { args->put_State(COREWEBVIEW2_PERMISSION_STATE_DENY); return S_OK; });
        web->add_PermissionRequested(permission.Get(),&token);
        auto popup=handler<ICoreWebView2NewWindowRequestedEventHandler,ICoreWebView2 *,ICoreWebView2NewWindowRequestedEventArgs *>(
            [](ICoreWebView2 *,ICoreWebView2NewWindowRequestedEventArgs *args) { args->put_Handled(TRUE); return S_OK; });
        web->add_NewWindowRequested(popup.Get(),&token);
        auto navigated=handler<ICoreWebView2NavigationCompletedEventHandler,ICoreWebView2 *,ICoreWebView2NavigationCompletedEventArgs *>(
            [this](ICoreWebView2 *,ICoreWebView2NavigationCompletedEventArgs *args) {
                BOOL success=FALSE;args->get_IsSuccess(&success);
                COREWEBVIEW2_WEB_ERROR_STATUS error;args->get_WebErrorStatus(&error);
                diagnostic(success ? "page loaded" : "navigation failed",static_cast<HRESULT>(error));
                if (!success && error != COREWEBVIEW2_WEB_ERROR_STATUS_OPERATION_CANCELED)
                    finish(22,"The market connection failed.");
                ComPtr<ICoreWebView2NavigationCompletedEventArgs2> response;
                if (SUCCEEDED(args->QueryInterface(IID_PPV_ARGS(&response)))) {
                    int status=0;response->get_HttpStatusCode(&status);diagnostic("HTTP response",static_cast<HRESULT>(status));
                }
                return S_OK;
            });
        web->add_NavigationCompleted(navigated.Get(),&token);
        HRESULT navigation=self_test ? web->NavigateToString(SELF_TEST) : web->Navigate(MARKET_URL);
        diagnostic("navigation requested",navigation);
        if (FAILED(navigation)) finish(12,"The market reader could not load its page.");
        return S_OK;
    }
    int run(HINSTANCE instance, decltype(&CreateCoreWebView2EnvironmentWithOptions) create, Options *options, const std::wstring &profile) {
        WNDCLASSW cls={};cls.hInstance=instance;cls.lpfnWndProc=messages;cls.lpszClassName=L"LupinMarketFetch";
        if (!RegisterClassW(&cls)) return 12;
        window=CreateWindowExW(WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE,cls.lpszClassName,L"Lupin market updater",WS_POPUP,0,0,800,600,nullptr,nullptr,instance,this);
        if (!window) return 12; // Never shown, activated, or attached to another application.
        auto callback=handler<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler,HRESULT,ICoreWebView2Environment *>(
            [this](HRESULT status,ICoreWebView2Environment *value) {
                diagnostic("environment",status);
                if (finished) return S_OK;
                if (FAILED(status) || !value) { finish(10,"The WebView2 runtime is unavailable."); return S_OK; }
                environment=value;
                auto completed=handler<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler,HRESULT,ICoreWebView2Controller *>(
                    [this](HRESULT result,ICoreWebView2Controller *value) { return created_controller(result,value); });
                if (FAILED(environment->CreateCoreWebView2Controller(window,completed.Get()))) finish(12,"The market reader could not create its view.");
                return S_OK;
            });
        SetTimer(window,1,200,nullptr);
        HRESULT creation=create(nullptr,profile.c_str(),options,callback.Get());
        diagnostic("environment requested",creation);
        if (FAILED(creation)) finish(10,"The WebView2 runtime is unavailable.");
        MSG message;
        while (GetMessageW(&message,nullptr,0,0)>0) { TranslateMessage(&message);DispatchMessageW(&message); }
        return exit_code;
    }
};

int WINAPI wWinMain(HINSTANCE instance,HINSTANCE,PWSTR,int) {
    int count=0;LPWSTR *argv=CommandLineToArgvW(GetCommandLineW(),&count);
    bool self_test=false,runtime_check=false,diagnostics=false,close=false;std::wstring profile;
    for (int i=1;i<count;i++) {
        if (!wcscmp(argv[i],L"--self-test")) self_test=true;
        else if (!wcscmp(argv[i],L"--diagnostic")) diagnostics=true;
        else if (!wcscmp(argv[i],L"--runtime-check")) runtime_check=true;
        else if (!wcscmp(argv[i],L"--close-panel")) close=true;
        else if (!wcscmp(argv[i],L"--profile") && i+1<count) profile=argv[++i];
        else if (!wcscmp(argv[i],L"--version")) { write_pipe(STD_OUTPUT_HANDLE,"Lupin market helper 1 (WebView2)\n");LocalFree(argv);return 0; }
        else { LocalFree(argv);return 2; }
    }
    LocalFree(argv);
    if (close) return close_panel(); // No WebView2 runtime or renderer is needed.
    for (const wchar_t *name : {L"WEBVIEW2_BROWSER_EXECUTABLE_FOLDER",L"WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",L"WEBVIEW2_PIPE_FOR_SCRIPT_DEBUGGER",L"WEBVIEW2_WAIT_FOR_SCRIPT_DEBUGGER",L"WEBVIEW2_RELEASE_CHANNELS",L"WEBVIEW2_CHANNEL_SEARCH_KIND"}) SetEnvironmentVariableW(name,nullptr);
    if (profile.empty() && !runtime_check) return 2;
    if (!profile.empty()) SetEnvironmentVariableW(L"WEBVIEW2_USER_DATA_FOLDER",profile.c_str());
    wchar_t path[32768];DWORD length=GetModuleFileNameW(nullptr,path,32768);
    if (!length || length>=32768) return 10;
    std::wstring dll(path);dll=dll.substr(0,dll.find_last_of(L"\\/")+1)+L"WebView2Loader.dll";
    HMODULE loader=LoadLibraryExW(dll.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!loader) return 10;
    auto available=reinterpret_cast<decltype(&GetAvailableCoreWebView2BrowserVersionStringWithOptions)>(GetProcAddress(loader,"GetAvailableCoreWebView2BrowserVersionStringWithOptions"));
    auto create=reinterpret_cast<decltype(&CreateCoreWebView2EnvironmentWithOptions)>(GetProcAddress(loader,"CreateCoreWebView2EnvironmentWithOptions"));
    if (!available || !create) return 10;
    if (FAILED(CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED))) return 12;
    ComPtr<Options> options;options.Attach(new Options());
    LPWSTR version=nullptr;HRESULT status=available(nullptr,options.Get(),&version);
    bool supported=SUCCEEDED(status) && version && wcstol(version,nullptr,10)>=124;
    CoTaskMemFree(version);
    if (!supported) { options.Reset();CoUninitialize();return 10; }
    if (runtime_check) { options.Reset();CoUninitialize();return 0; }
    // This unnamed job owns only this helper and descendants started for its private profile.
    // Its handle intentionally lives until process exit, including forced cancellation.
    HANDLE job=CreateJobObjectW(nullptr,nullptr);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits={};limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!job || !SetInformationJobObject(job,JobObjectExtendedLimitInformation,&limits,sizeof(limits)) || !AssignProcessToJobObject(job,GetCurrentProcess())) {
        options.Reset();CoUninitialize();return 12;
    }
    SetPriorityClass(GetCurrentProcess(),BELOW_NORMAL_PRIORITY_CLASS);
    int code;
    { MarketReader reader(self_test,diagnostics);code=reader.run(instance,create,options.Get(),profile); }
    options.Reset();CoUninitialize();return code;
}
