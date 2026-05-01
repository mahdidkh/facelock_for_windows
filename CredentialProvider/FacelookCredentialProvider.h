/*
 * FacelookCredentialProvider.h
 * ================================
 * Windows Credential Provider COM DLL — Header
 *
 * Implements the official Microsoft Credential Provider v2 interfaces:
 *   - ICredentialProvider
 *   - ICredentialProviderCredential2
 *
 * Communication with the Python face service via Named Pipe.
 *
 * Compile: Visual Studio 2022 / C++17 / x64
 * Link:    credui.lib, ole32.lib, uuid.lib
 */

#pragma once

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <unknwn.h>
#include <credentialprovider.h>
#include <ntstatus.h>
#include <strsafe.h>
#include <shlguid.h>

// ── CLSID for this provider ──────────────────────────────────────────────────
// Generate your own with: uuidgen.exe
// Then register in: HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\
//                   Authentication\Credential Providers\{YOUR-CLSID}
//
// {A1B2C3D4-E5F6-7890-ABCD-EF1234567890}  <-- REPLACE WITH YOUR OWN
DEFINE_GUID(CLSID_FacelookCredentialProvider,
    0xa1b2c3d4, 0xe5f6, 0x7890,
    0xab, 0xcd, 0xef, 0x12, 0x34, 0x56, 0x78, 0x90);

// ── Named Pipe ────────────────────────────────────────────────────────────────
#define FACELOOK_PIPE_NAME  L"\\\\.\\pipe\\FacelookBiometric"
#define PIPE_BUFFER_SIZE    65536
#define PIPE_TIMEOUT_MS     8000    // 8 seconds max for face scan

// ── Provider string resources ─────────────────────────────────────────────────
#define FACELOOK_LABEL      L"FACELOOK — Face Recognition"
#define FACELOOK_STATUS_MSG L"Scanning face..."


// ============================================================================
//  FacelookCredential
//  Represents a single credential tile on the login screen
// ============================================================================
class FacelookCredential : public ICredentialProviderCredential2
{
public:
    // IUnknown
    STDMETHOD(QueryInterface)(REFIID riid, void** ppv);
    STDMETHOD_(ULONG, AddRef)();
    STDMETHOD_(ULONG, Release)();

    // ICredentialProviderCredential
    STDMETHOD(Advise)(ICredentialProviderCredentialEvents* pcpce);
    STDMETHOD(UnAdvise)();
    STDMETHOD(SetSelected)(BOOL* pbAutoLogon);
    STDMETHOD(SetDeselected)();
    STDMETHOD(GetFieldState)(DWORD dwFieldID,
                             CREDENTIAL_PROVIDER_FIELD_STATE* pcpfs,
                             CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* pcpfis);
    STDMETHOD(GetStringValue)(DWORD dwFieldID, PWSTR* ppwsz);
    STDMETHOD(GetBitmapValue)(DWORD dwFieldID, HBITMAP* phbmp);
    STDMETHOD(GetCheckboxValue)(DWORD dwFieldID, BOOL* pbChecked, PWSTR* ppwszLabel);
    STDMETHOD(GetSubmitButtonValue)(DWORD dwFieldID, DWORD* pdwAdjacentTo);
    STDMETHOD(GetComboBoxValueCount)(DWORD dwFieldID, DWORD* pcItems, DWORD* pdwSelectedItem);
    STDMETHOD(GetComboBoxValueAt)(DWORD dwFieldID, DWORD dwItem, PWSTR* ppwszItem);
    STDMETHOD(SetStringValue)(DWORD dwFieldID, PCWSTR pwz);
    STDMETHOD(SetCheckboxValue)(DWORD dwFieldID, BOOL bChecked);
    STDMETHOD(SetComboBoxSelectedValue)(DWORD dwFieldID, DWORD dwSelectedItem);
    STDMETHOD(CommandLinkClicked)(DWORD dwFieldID);
    STDMETHOD(GetSerialization)(CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* pcpgsr,
                                CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs,
                                PWSTR* ppwszOptionalStatusText,
                                CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon);
    STDMETHOD(ReportResult)(NTSTATUS ntsStatus, NTSTATUS ntsSubstatus,
                            PWSTR* ppwszOptionalStatusText,
                            CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon);

    // ICredentialProviderCredential2
    STDMETHOD(GetUserSid)(PWSTR* ppszSid);

    // Construction / initialization
    FacelookCredential();
    ~FacelookCredential();
    HRESULT Initialize(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus,
                       ICredentialProviderUser* pUser);

private:
    LONG    _cRef;
    PWSTR   _pszUsername;
    PWSTR   _pszUserSid;
    PWSTR   _pszPassword;          // Retrieved securely after face auth
    CREDENTIAL_PROVIDER_USAGE_SCENARIO _cpus;
    ICredentialProviderCredentialEvents* _pCredProvCredentialEvents;

    // Named Pipe communication
    HRESULT _SendPipeCommand(LPCSTR jsonRequest, LPSTR jsonResponse, DWORD cbResponse);
    HRESULT _RunFaceAuthentication(PWSTR* ppwszUsername);
};


// ============================================================================
//  FacelookCredentialProvider
//  The factory that creates credential tiles
// ============================================================================
class FacelookCredentialProvider : public ICredentialProvider
{
public:
    // IUnknown
    STDMETHOD(QueryInterface)(REFIID riid, void** ppv);
    STDMETHOD_(ULONG, AddRef)();
    STDMETHOD_(ULONG, Release)();

    // ICredentialProvider
    STDMETHOD(SetUsageScenario)(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, DWORD dwFlags);
    STDMETHOD(SetSerialization)(const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs);
    STDMETHOD(Advise)(ICredentialProviderEvents* pcpe, UINT_PTR upAdviseContext);
    STDMETHOD(UnAdvise)();
    STDMETHOD(GetFieldDescriptorCount)(DWORD* pdwCount);
    STDMETHOD(GetFieldDescriptorAt)(DWORD dwIndex,
                                    CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppcpfd);
    STDMETHOD(GetCredentialCount)(DWORD* pdwCount,
                                  DWORD* pdwDefault,
                                  BOOL*  pbAutoLogonWithDefault);
    STDMETHOD(GetCredentialAt)(DWORD dwIndex,
                               ICredentialProviderCredential** ppcpc);

    FacelookCredentialProvider();
    ~FacelookCredentialProvider();

private:
    LONG     _cRef;
    DWORD    _dwNumCreds;
    CREDENTIAL_PROVIDER_USAGE_SCENARIO _cpus;
    FacelookCredential** _rgpCredentials;
};


// ============================================================================
//  DLL Exports (required for COM registration)
// ============================================================================
HRESULT FacelookCredentialProvider_CreateInstance(REFIID riid, void** ppv);
