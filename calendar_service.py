"""
Google Calendar API連携モジュール
OAuth 2.0認証と予定取得機能を提供
"""

import os
import json
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Google Calendar APIのスコープ
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

# 認証情報ディレクトリ
CREDENTIALS_DIR = os.path.join(os.path.dirname(__file__), 'credentials')
CLIENT_SECRETS_FILE = os.path.join(CREDENTIALS_DIR, 'credentials.json')

# 管理するアカウント
ACCOUNTS = [
    {'id': 'account1', 'email': 'keiggoo.0527@gmail.com'},
    {'id': 'account2', 'email': 'yoshinaga_k@butaifarm.com'}
]


def get_token_path(account_id):
    """アカウントIDに対応するトークンファイルパスを取得"""
    return os.path.join(CREDENTIALS_DIR, f'token_{account_id}.json')


def get_credentials(account_id):
    """
    指定アカウントの認証情報を取得
    トークンが存在し有効な場合はそれを使用、なければNoneを返す
    """
    token_path = get_token_path(account_id)
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # トークンが期限切れの場合、リフレッシュを試みる
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(account_id, creds)
        except Exception:
            creds = None

    return creds


def save_credentials(account_id, creds):
    """認証情報をファイルに保存"""
    token_path = get_token_path(account_id)
    with open(token_path, 'w') as token_file:
        token_file.write(creds.to_json())


def create_auth_flow(account_id, redirect_uri):
    """
    OAuth 2.0認証フローを作成
    """
    if not os.path.exists(CLIENT_SECRETS_FILE):
        raise FileNotFoundError(
            f"credentials.json が見つかりません。"
            f"Google Cloud Consoleからダウンロードして {CREDENTIALS_DIR} に配置してください。"
        )

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )

    return flow


def get_auth_url(account_id, redirect_uri):
    """
    OAuth認証URLを生成
    """
    flow = create_auth_flow(account_id, redirect_uri)
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return auth_url, state


def complete_auth(account_id, authorization_response, redirect_uri):
    """
    OAuth認証を完了し、トークンを保存
    """
    flow = create_auth_flow(account_id, redirect_uri)
    flow.fetch_token(authorization_response=authorization_response)
    creds = flow.credentials
    save_credentials(account_id, creds)
    return creds


def get_calendar_service(account_id):
    """
    Google Calendar APIサービスを取得
    """
    creds = get_credentials(account_id)
    if not creds or not creds.valid:
        return None

    return build('calendar', 'v3', credentials=creds)


def get_events(account_id, time_min, time_max):
    """
    指定期間の予定を取得

    Args:
        account_id: アカウントID
        time_min: 開始日時 (datetime)
        time_max: 終了日時 (datetime)

    Returns:
        list: 予定のリスト [{'start': datetime, 'end': datetime, 'summary': str}, ...]
    """
    service = get_calendar_service(account_id)
    if not service:
        raise ValueError(f"アカウント {account_id} の認証が必要です")

    # RFC3339形式に変換
    time_min_str = time_min.isoformat() + 'Z' if time_min.tzinfo is None else time_min.isoformat()
    time_max_str = time_max.isoformat() + 'Z' if time_max.tzinfo is None else time_max.isoformat()

    events_result = service.events().list(
        calendarId='primary',
        timeMin=time_min_str,
        timeMax=time_max_str,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    result = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))

        # 終日イベントの場合は日付のみ
        if 'T' in start:
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
        else:
            # 終日イベント
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)

        result.append({
            'start': start_dt,
            'end': end_dt,
            'summary': event.get('summary', '(タイトルなし)'),
            'all_day': 'T' not in start
        })

    return result


def get_all_accounts_events(time_min, time_max):
    """
    全アカウントの予定を取得

    Returns:
        dict: {account_id: [events], ...}
    """
    all_events = {}
    for account in ACCOUNTS:
        try:
            events = get_events(account['id'], time_min, time_max)
            all_events[account['id']] = events
        except ValueError as e:
            all_events[account['id']] = {'error': str(e)}

    return all_events


def get_auth_status():
    """
    各アカウントの認証状態を取得
    """
    status = {}
    for account in ACCOUNTS:
        creds = get_credentials(account['id'])
        status[account['id']] = {
            'email': account['email'],
            'authenticated': creds is not None and creds.valid
        }
    return status


def is_all_authenticated():
    """
    全アカウントが認証済みかどうか
    """
    status = get_auth_status()
    return all(s['authenticated'] for s in status.values())


def load_credentials_from_env():
    """
    環境変数から認証情報を読み込みファイルに保存
    Render等のクラウド環境用

    環境変数:
        GOOGLE_CREDENTIALS: credentials.json の内容（JSON文字列）
        TOKEN_ACCOUNT1: account1 のトークン（JSON文字列）
        TOKEN_ACCOUNT2: account2 のトークン（JSON文字列）
    """
    # credentialsディレクトリ作成
    if not os.path.exists(CREDENTIALS_DIR):
        os.makedirs(CREDENTIALS_DIR)

    # credentials.json
    google_creds = os.environ.get('GOOGLE_CREDENTIALS')
    if google_creds:
        try:
            # JSON形式の検証
            json.loads(google_creds)
            with open(CLIENT_SECRETS_FILE, 'w') as f:
                f.write(google_creds)
        except json.JSONDecodeError:
            print("Warning: GOOGLE_CREDENTIALS is not valid JSON")

    # トークンファイル
    for account in ACCOUNTS:
        env_var = f"TOKEN_{account['id'].upper()}"
        token_data = os.environ.get(env_var)
        if token_data:
            try:
                json.loads(token_data)
                token_path = get_token_path(account['id'])
                with open(token_path, 'w') as f:
                    f.write(token_data)
            except json.JSONDecodeError:
                print(f"Warning: {env_var} is not valid JSON")
