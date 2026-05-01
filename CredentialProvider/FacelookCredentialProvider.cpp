/*
 * FacelookCredentialProvider.cpp
 * =================================
 * Windows Credential Provider COM DLL — Implementation
 *
 * Flow:
 *   1. Windows calls SetUsageScenario() at login screen load
 *   2. Windows calls GetCredentialAt() → returns our FacelookCredential tile
 *   3. User selects face tile → SetSelected() triggers face scan
 *   4. GetSerialization() sends face result → Windows finalizes session
 *
 * Named Pipe protocol (JSON):
 *   Request:  {"command": "authenticate"}
 *   Response: {"success": true, "username": "John", "score": 0.97}
 */

#include "FacelookCredentialProvider.h"
#include <wincred.h>
#include <lm.h>
#include <shlwapi.h>

#pragma comment(lib, "credui.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "shlwapi.lib")

// Simple JSON value extractor (no external dependency)
static bool ExtractJsonString(LPCSTR json, LPCSTR key, LPSTR outBuf, DWORD cbBuf) {
    char search[128];
    sprintf_s(search, "\"%s\":\"", key);
    LPCSTR pos = strstr(json, search);
    if (!pos) return false;
    pos += strlen(search);
    LPCSTR end = strchr(pos, '"');
    if (!end) return false;
    DWORD len = (DWORD)(end - pos);
    if (len >= cbBuf) return false;
    strncpy_s(outBuf, cbBuf, pos, len);
    return true;
}

static bool ExtractJsonBool(LPCSTR json, LPCSTR key) {
    char search[128];
    sprintf_s(search, "\"%s\":true", key);
    return strstr(json, search) != nullptr;
}


// ============================================================================
//  FacelookCredential Implementation
// ============================================================================

FacelookCredential::FacelookCredential()
    : _cRef(1), _pszUsername(nullptr), _pszUserSid(nullptr),
      _pszPassword(nullptr), _pCredProvCredentialEvents(nullptr)
{
}

FacelookCredential::~FacelookCredential() {
    CoTaskMemFree(_pszUsername);
    CoTaskMemFree(_pszUserSid);
    SecureZeroMemory(_pszPassword, _pszPassword ? wcslen(_pszPassword) * sizeof(WCHAR) : 0);
    CoTaskMemFree(_pszPassword);
    if (_pCredProvCredentialEvents)
        _pCredProvCredentialEvents->Release();
}

HRESULT FacelookCredential::Initialize(
    CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus,
    ICredentialProviderUser* pUser)
{
    _cpus = cpus;
    PWSTR pszSid = nullptr;
    HRESULT hr = pUser->GetSid(&pszSid);
    if (SUCCEEDED(hr)) {
        hr = SHStrDupW(pszSid, &_pszUserSid);
        CoTaskMemFree(pszSid);
    }
    if (SUCCEEDED(hr)) {
        PWSTR pszName = nullptr;
        hr = pUser->GetStringValue(PKEY_Identity_UserName, &pszName);
        if (SUCCEEDED(hr)) {
            hr = SHStrDupW(pszName, &_pszUsername);
            CoTaskMemFree(pszName);
        }
    }
    return hr;
}

// IUnknown
STDMETHODIMP FacelookCredential::QueryInterface(REFIID riid, void** ppv) {
    if (riid == IID_IUnknown || riid == IID_ICredentialProviderCredential)
        *ppv = static_cast<ICredentialProviderCredential*>(this);
    else if (riid == IID_ICredentialProviderCredential2)
        *ppv = static_cast<ICredentialProviderCredential2*>(this);
    else { *ppv = nullptr; return E_NOINTERFACE; }
    AddRef(); return S_OK;
}
STDMETHODIMP_(ULONG) FacelookCredential::AddRef()  { return InterlockedIncrement(&_cRef); }
STDMETHODIMP_(ULONG) FacelookCredential::Release() {
    ULONG r = InterlockedDecrement(&_cRef);
    if (!r) delete this;
    return r;
}

STDMETHODIMP FacelookCredential::Advise(ICredentialProviderCredentialEvents* pcpce) {
    if (_pCredProvCredentialEvents) _pCredProvCredentialEvents->Release();
    _pCredProvCredentialEvents = pcpce;
    if (_pCredProvCredentialEvents) _pCredProvCredentialEvents->AddRef();
    return S_OK;
}
STDMETHODIMP FacelookCredential::UnAdvise() {
    if (_pCredProvCredentialEvents) {
        _pCredProvCredentialEvents->Release();
        _pCredProvCredentialEvents = nullptr;
    }
    return S_OK;
}

STDMETHODIMP FacelookCredential::SetSelected(BOOL* pbAutoLogon) {
    // Trigger face scan automatically when tile is selected
    *pbAutoLogon = FALSE;
    PWSTR pszRecognized = nullptr;
    HRESULT hr = _RunFaceAuthentication(&pszRecognized);
    if (SUCCEEDED(hr) && pszRecognized) {
        *pbAutoLogon = TRUE;
        CoTaskMemFree(pszRecognized);
    }
    return S_OK;
}
STDMETHODIMP FacelookCredential::SetDeselected() { return S_OK; }

STDMETHODIMP FacelookCredential::GetStringValue(DWORD dwFieldID, PWSTR* ppwsz) {
    switch (dwFieldID) {
        case 0: return SHStrDupW(FACELOOK_LABEL, ppwsz);
        case 1: return SHStrDupW(_pszUsername ? _pszUsername : L"User", ppwsz);
        case 2: return SHStrDupW(FACELOOK_STATUS_MSG, ppwsz);
        default: *ppwsz = nullptr; return E_INVALIDARG;
    }
}

STDMETHODIMP FacelookCredential::GetSerialization(
    CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* pcpgsr,
    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs,
    PWSTR* ppwszOptionalStatusText,
    CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon)
{
    PWSTR pszRecognized = nullptr;
    HRESULT hr = _RunFaceAuthentication(&pszRecognized);

    if (FAILED(hr) || !pszRecognized) {
        *pcpgsr = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
        SHStrDupW(L"Face not recognized. Access denied.", ppwszOptionalStatusText);
        *pcpsiOptionalStatusIcon = CPSI_ERROR;
        return S_OK;
    }

    // Build KERB_INTERACTIVE_UNLOCK_LOGON serialization
    // In a real implementation, fetch the Windows token here.
    // For the prototype, we signal success to LSASS.
    *pcpgsr = CPGSR_RETURN_CREDENTIAL_FINISHED;
    *pcpsiOptionalStatusIcon = CPSI_SUCCESS;
    SHStrDupW(L"Face recognized! Welcome.", ppwszOptionalStatusText);
    CoTaskMemFree(pszRecognized);
    return S_OK;
}

STDMETHODIMP FacelookCredential::ReportResult(
    NTSTATUS ntsStatus, NTSTATUS ntsSubstatus,
    PWSTR* ppwszOptionalStatusText,
    CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon)
{
    *ppwszOptionalStatusText = nullptr;
    *pcpsiOptionalStatusIcon = CPSI_NONE;
    return S_OK;
}

STDMETHODIMP FacelookCredential::GetUserSid(PWSTR* ppszSid) {
    return SHStrDupW(_pszUserSid ? _pszUserSid : L"", ppszSid);
}

// ── Named Pipe Communication ──────────────────────────────────────────────────

HRESULT FacelookCredential::_SendPipeCommand(
    LPCSTR jsonRequest, LPSTR jsonResponse, DWORD cbResponse)
{
    HANDLE hPipe = CreateFileW(
        FACELOOK_PIPE_NAME,
        GENERIC_READ | GENERIC_WRITE, 0, nullptr,
        OPEN_EXISTING, 0, nullptr
    );

    if (hPipe == INVALID_HANDLE_VALUE) {
        // Service might be starting — wait and retry once
        WaitNamedPipeW(FACELOOK_PIPE_NAME, PIPE_TIMEOUT_MS);
        hPipe = CreateFileW(
            FACELOOK_PIPE_NAME,
            GENERIC_READ | GENERIC_WRITE, 0, nullptr,
            OPEN_EXISTING, 0, nullptr
        );
        if (hPipe == INVALID_HANDLE_VALUE)
            return HRESULT_FROM_WIN32(GetLastError());
    }

    DWORD mode = PIPE_READMODE_MESSAGE;
    SetNamedPipeHandleState(hPipe, &mode, nullptr, nullptr);

    // Write request
    DWORD cbWritten = 0;
    BOOL ok = WriteFile(hPipe, jsonRequest, (DWORD)strlen(jsonRequest), &cbWritten, nullptr);
    if (!ok) { CloseHandle(hPipe); return HRESULT_FROM_WIN32(GetLastError()); }

    // Read response
    DWORD cbRead = 0;
    ok = ReadFile(hPipe, jsonResponse, cbResponse - 1, &cbRead, nullptr);
    CloseHandle(hPipe);
    if (!ok) return HRESULT_FROM_WIN32(GetLastError());

    jsonResponse[cbRead] = '\0';
    return S_OK;
}

HRESULT FacelookCredential::_RunFaceAuthentication(PWSTR* ppwszUsername) {
    char response[PIPE_BUFFER_SIZE] = {};
    HRESULT hr = _SendPipeCommand(
        "{\"command\":\"authenticate\"}",
        response, sizeof(response)
    );
    if (FAILED(hr)) return hr;

    if (!ExtractJsonBool(response, "success"))
        return E_FAIL;

    char name[256] = {};
    if (!ExtractJsonString(response, "username", name, sizeof(name)))
        return E_FAIL;

    // Convert to wide string
    int len = MultiByteToWideChar(CP_UTF8, 0, name, -1, nullptr, 0);
    *ppwszUsername = (PWSTR)CoTaskMemAlloc(len * sizeof(WCHAR));
    if (!*ppwszUsername) return E_OUTOFMEMORY;
    MultiByteToWideChar(CP_UTF8, 0, name, -1, *ppwszUsername, len);
    return S_OK;
}

// Stub implementations for unused interface methods
STDMETHODIMP FacelookCredential::GetFieldState(DWORD, CREDENTIAL_PROVIDER_FIELD_STATE* s, CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* i) {
    *s = CPFS_DISPLAY_IN_SELECTED_TILE; *i = CPFIS_NONE; return S_OK;
}
STDMETHODIMP FacelookCredential::GetBitmapValue(DWORD, HBITMAP* p) { *p = nullptr; return E_NOTIMPL; }
STDMETHODIMP FacelookCredential::GetCheckboxValue(DWORD, BOOL*, PWSTR*) { return E_NOTIMPL; }
STDMETHODIMP FacelookCredential::GetSubmitButtonValue(DWORD, DWORD* p) { *p = 0; return S_OK; }
STDMETHODIMP FacelookCredential::GetComboBoxValueCount(DWORD, DWORD*, DWORD*) { return E_NOTIMPL; }
STDMETHODIMP FacelookCredential::GetComboBoxValueAt(DWORD, DWORD, PWSTR*) { return E_NOTIMPL; }
STDMETHODIMP FacelookCredential::SetStringValue(DWORD, PCWSTR) { return S_OK; }
STDMETHODIMP FacelookCredential::SetCheckboxValue(DWORD, BOOL) { return E_NOTIMPL; }
STDMETHODIMP FacelookCredential::SetComboBoxSelectedValue(DWORD, DWORD) { return E_NOTIMPL; }
STDMETHODIMP FacelookCredential::CommandLinkClicked(DWORD) { return E_NOTIMPL; }


// ============================================================================
//  FacelookCredentialProvider Implementation
// ============================================================================

FacelookCredentialProvider::FacelookCredentialProvider()
    : _cRef(1), _dwNumCreds(0), _rgpCredentials(nullptr) {}

FacelookCredentialProvider::~FacelookCredentialProvider() {
    if (_rgpCredentials) {
        for (DWORD i = 0; i < _dwNumCreds; i++)
            if (_rgpCredentials[i]) _rgpCredentials[i]->Release();
        delete[] _rgpCredentials;
    }
}

STDMETHODIMP FacelookCredentialProvider::QueryInterface(REFIID riid, void** ppv) {
    if (riid == IID_IUnknown || riid == IID_ICredentialProvider)
        *ppv = static_cast<ICredentialProvider*>(this);
    else { *ppv = nullptr; return E_NOINTERFACE; }
    AddRef(); return S_OK;
}
STDMETHODIMP_(ULONG) FacelookCredentialProvider::AddRef()  { return InterlockedIncrement(&_cRef); }
STDMETHODIMP_(ULONG) FacelookCredentialProvider::Release() {
    ULONG r = InterlockedDecrement(&_cRef);
    if (!r) delete this;
    return r;
}

STDMETHODIMP FacelookCredentialProvider::SetUsageScenario(
    CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, DWORD)
{
    // Support lock screen and workstation unlock
    switch (cpus) {
        case CPUS_LOGON:
        case CPUS_UNLOCK_WORKSTATION:
        case CPUS_CREDUI:
            _cpus = cpus;
            return S_OK;
        default:
            return E_NOTIMPL;
    }
}

STDMETHODIMP FacelookCredentialProvider::GetCredentialCount(
    DWORD* pdwCount, DWORD* pdwDefault, BOOL* pbAutoLogonWithDefault)
{
    *pdwCount = _dwNumCreds;
    *pdwDefault = (_dwNumCreds > 0) ? 0 : CREDENTIAL_PROVIDER_NO_DEFAULT;
    *pbAutoLogonWithDefault = FALSE;
    return S_OK;
}

STDMETHODIMP FacelookCredentialProvider::GetCredentialAt(
    DWORD dwIndex, ICredentialProviderCredential** ppcpc)
{
    if (dwIndex >= _dwNumCreds || !ppcpc) return E_INVALIDARG;
    return _rgpCredentials[dwIndex]->QueryInterface(
        IID_ICredentialProviderCredential, (void**)ppcpc
    );
}

STDMETHODIMP FacelookCredentialProvider::GetFieldDescriptorCount(DWORD* pdwCount) {
    *pdwCount = 3;   // Label, username display, status text
    return S_OK;
}

STDMETHODIMP FacelookCredentialProvider::GetFieldDescriptorAt(
    DWORD dwIndex, CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppcpfd)
{
    static CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR fields[] = {
        { 0, CPFT_LARGE_TEXT,    L"Facelook Label",  CPFG_CREDENTIAL_PROVIDER_LABEL },
        { 1, CPFT_SMALL_TEXT,    L"Username",        CPFG_LOGON_USERNAME            },
        { 2, CPFT_SMALL_TEXT,    L"Status",          CPFG_CREDENTIAL_PROVIDER_LOGO  },
    };
    if (dwIndex >= 3) return E_INVALIDARG;
    *ppcpfd = (CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR*)CoTaskMemAlloc(sizeof(**ppcpfd));
    if (!*ppcpfd) return E_OUTOFMEMORY;
    **ppcpfd = fields[dwIndex];
    return S_OK;
}

STDMETHODIMP FacelookCredentialProvider::SetSerialization(
    const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION*) { return E_NOTIMPL; }
STDMETHODIMP FacelookCredentialProvider::Advise(ICredentialProviderEvents*, UINT_PTR) { return S_OK; }
STDMETHODIMP FacelookCredentialProvider::UnAdvise() { return S_OK; }


// ============================================================================
//  DLL COM Factory
// ============================================================================

HRESULT FacelookCredentialProvider_CreateInstance(REFIID riid, void** ppv) {
    auto* pProvider = new (std::nothrow) FacelookCredentialProvider();
    if (!pProvider) return E_OUTOFMEMORY;
    HRESULT hr = pProvider->QueryInterface(riid, ppv);
    pProvider->Release();
    return hr;
}

// Standard DLL exports
STDAPI DllCanUnloadNow()  { return S_OK; }
STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv) {
    if (rclsid != CLSID_FacelookCredentialProvider) return CLASS_E_CLASSNOTAVAILABLE;
    return FacelookCredentialProvider_CreateInstance(riid, ppv);
}
