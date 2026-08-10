#!/usr/bin/env python3
"""GSC OAuth 一次性授權。

用法：
    python3 tools/gsc_auth.py

會開啟瀏覽器要你選 Google 帳號並同意，成功後把憑證寫進
~/.config/gsc/token.json，之後 gsc_fetch.py 就不需要再授權。

前置：把 Google Cloud 下載的「桌面應用程式」OAuth 用戶端 JSON
放到 ~/.config/gsc/client_secret.json（設定步驟見 tools/README.md）。
"""
import os
import sys
import pathlib

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
CONF = pathlib.Path(os.environ.get("GSC_CONFIG_DIR", pathlib.Path.home() / ".config" / "gsc"))
CLIENT_SECRET = CONF / "client_secret.json"
TOKEN = CONF / "token.json"


def main():
    CONF.mkdir(parents=True, exist_ok=True)
    if not CLIENT_SECRET.exists():
        sys.exit(
            f"找不到 {CLIENT_SECRET}\n"
            "請先到 Google Cloud Console 建立「桌面應用程式」類型的 OAuth 用戶端，\n"
            "下載 JSON 後放到上述路徑（詳見 tools/README.md）。"
        )

    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        if creds.valid:
            print(f"已有有效憑證：{TOKEN}")
            return
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN.write_text(creds.to_json())
            print(f"憑證已更新：{TOKEN}")
            return

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    TOKEN.write_text(creds.to_json())
    os.chmod(TOKEN, 0o600)
    print(f"授權完成，憑證已寫入 {TOKEN}")
    print("接著可以跑：python3 tools/gsc_fetch.py --list")


if __name__ == "__main__":
    main()
