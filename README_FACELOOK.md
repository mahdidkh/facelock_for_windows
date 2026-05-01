# FACELOOK - Biometric Login System

This project is a Windows Biometric Authentication System (Credential Provider) that integrates directly with the Windows Login Screen. It uses advanced deep learning (MTCNN + ArcFace) to recognize faces and unlock the computer, adhering to strict security and privacy standards (AES-256 encryption, no raw image storage).

## 🏗️ Architecture

1. **CredentialProvider.dll (C++)**: The native Windows COM plugin that displays the face scan UI on the lock screen.
2. **FaceRecognitionService (Python)**: A background Windows Service that handles camera capture, liveness detection, and facial recognition.
3. **Named Pipes**: Secure local communication between the DLL and the Python service.
4. **SecureStorage (SQLite + AES-256)**: Encrypted database storing only biometric vectors (no images).

## 🚀 Step-by-Step Setup Guide

### Phase 1: Python Environment & AI Engine

1. **Install dependencies:**
   Open a terminal as Administrator and run:
   ```cmd
   pip install -r requirements.txt
   ```

2. **Enroll a User:**
   To test the AI pipeline and register your face, use the enrollment tool:
   ```cmd
   python SecureStorage/enrollment.py --enroll --username "YourWindowsUsername"
   ```
   *(Look at the camera and press Space to capture).*

3. **Test Live Authentication:**
   Verify the engine recognizes you correctly:
   ```cmd
   python SecureStorage/enrollment.py --test
   ```

### Phase 2: Windows Service Setup

The Python AI engine must run as a Windows Service so it's active even when no user is logged in (at the lock screen).

1. **Install the service:**
   Open an **Administrator** command prompt:
   ```cmd
   python FaceService/service_main.py install
   ```

2. **Start the service:**
   ```cmd
   python FaceService/service_main.py start
   ```
   *(You can also manage it via `services.msc`, look for "Facelook Biometric Recognition Service")*

### Phase 3: Compile the C++ Credential Provider DLL

1. Install **Visual Studio 2022** with the "Desktop development with C++" workload.
2. Create a new "Dynamic-Link Library (DLL)" project named `CredentialProvider`.
3. Add the three files from the `CredentialProvider/` folder to your project:
   - `FacelookCredentialProvider.h`
   - `FacelookCredentialProvider.cpp`
   - `FacelookCredentialProvider.def`
4. Set the project properties to **x64** and **Release**.
5. Build the project. You will get a `CredentialProvider.dll` file.
6. Copy the compiled `CredentialProvider.dll` to `C:\FacelookBiometric\` (Create this folder if it doesn't exist).

### Phase 4: Install the Credential Provider

1. Open `Installer/install.reg` to register the COM DLL with Windows.
2. Press **Win + L** to lock your screen.
3. You should see a new "Facelook" login option. Click it, and it will communicate with your background service to scan your face!

## 🗑️ Uninstallation

If you need to remove the system:
1. Run `Installer/uninstall.reg`.
2. Stop and remove the Windows Service:
   ```cmd
   python FaceService/service_main.py stop
   python FaceService/service_main.py remove
   ```

## 🛡️ Security Compliance
- **No Raw Images**: The system only stores encrypted mathematical vectors (`numpy` embeddings).
- **AES-256-GCM**: All biometric data is encrypted at rest in the SQLite vault.
- **Liveness Detection**: Implements passive liveness checks to prevent spoofing with photos or screens.
- **IPC Security**: The Named Pipe enforces strict ACLs (Local System & Admins only).
