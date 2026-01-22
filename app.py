"""
Googleカレンダー空き時間検索Webアプリ
Flask メインアプリケーション
"""

import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.middleware.proxy_fix import ProxyFix

from calendar_service import (
    get_auth_status, get_auth_url, complete_auth,
    get_all_accounts_events, is_all_authenticated, ACCOUNTS,
    load_credentials_from_env
)
from availability import (
    find_available_slots, format_candidates, parse_date_query
)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# プロキシ対応（Renderなどのリバースプロキシ環境用）
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# 環境変数から認証情報を読み込み
load_credentials_from_env()

# OAuth コールバックURI
def get_redirect_uri():
    # HTTPSを強制（本番環境用）
    url = request.url_root.rstrip('/')
    if os.environ.get('RENDER') and url.startswith('http://'):
        url = url.replace('http://', 'https://', 1)
    return url + '/oauth2callback'


@app.route('/')
def index():
    """メインページ"""
    auth_status = get_auth_status()
    return render_template('index.html', auth_status=auth_status)


@app.route('/auth/status')
def auth_status():
    """認証状態を返すAPI"""
    status = get_auth_status()
    all_authenticated = is_all_authenticated()
    return jsonify({
        'accounts': status,
        'all_authenticated': all_authenticated
    })


@app.route('/auth/<account_id>')
def start_auth(account_id):
    """OAuth認証を開始"""
    # アカウントIDの検証
    valid_ids = [a['id'] for a in ACCOUNTS]
    if account_id not in valid_ids:
        return jsonify({'error': '無効なアカウントIDです'}), 400

    try:
        redirect_uri = get_redirect_uri()
        auth_url, state = get_auth_url(account_id, redirect_uri)

        # セッションに状態を保存
        session['oauth_state'] = state
        session['oauth_account_id'] = account_id

        return redirect(auth_url)
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 500


@app.route('/oauth2callback')
def oauth_callback():
    """OAuth認証コールバック"""
    account_id = session.get('oauth_account_id')
    if not account_id:
        return "認証セッションが見つかりません", 400

    try:
        redirect_uri = get_redirect_uri()
        complete_auth(account_id, request.url, redirect_uri)

        # セッションをクリア
        session.pop('oauth_state', None)
        session.pop('oauth_account_id', None)

        return redirect(url_for('index'))
    except Exception as e:
        return f"認証エラー: {str(e)}", 500


@app.route('/search', methods=['POST'])
def search_availability():
    """空き時間を検索するAPI"""
    # 認証チェック
    if not is_all_authenticated():
        return jsonify({
            'error': 'すべてのアカウントで認証が必要です',
            'need_auth': True
        }), 401

    data = request.get_json()
    query = data.get('query', '今週の候補日')

    try:
        # クエリを解析
        params = parse_date_query(query)

        # 予定を取得
        events = get_all_accounts_events(
            params['start_date'],
            params['end_date']
        )

        # エラーチェック
        for account_id, account_events in events.items():
            if isinstance(account_events, dict) and 'error' in account_events:
                return jsonify({
                    'error': account_events['error'],
                    'need_auth': True
                }), 401

        # 空き時間を検索
        slots = find_available_slots(
            events,
            params['start_date'],
            params['end_date'],
            slot_duration=params['slot_duration'],
            work_start=params['work_start'],
            work_end=params['work_end'],
            max_candidates=params['max_candidates']
        )

        # フォーマット
        result = format_candidates(slots)

        return jsonify({
            'success': True,
            'result': result,
            'slots': [
                {
                    'start': slot['start'].isoformat(),
                    'end': slot['end'].isoformat()
                }
                for slot in slots
            ],
            'query_params': {
                'start_date': params['start_date'].isoformat(),
                'end_date': params['end_date'].isoformat(),
                'slot_duration': params['slot_duration'],
                'work_start': params['work_start'].strftime('%H:%M'),
                'work_end': params['work_end'].strftime('%H:%M'),
                'max_candidates': params['max_candidates']
            }
        })

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'エラーが発生しました: {str(e)}'}), 500


@app.route('/logout/<account_id>')
def logout(account_id):
    """アカウントのトークンを削除"""
    from calendar_service import get_token_path
    token_path = get_token_path(account_id)
    if os.path.exists(token_path):
        os.remove(token_path)
    return redirect(url_for('index'))


if __name__ == '__main__':
    # credentialsディレクトリが存在しない場合は作成
    credentials_dir = os.path.join(os.path.dirname(__file__), 'credentials')
    if not os.path.exists(credentials_dir):
        os.makedirs(credentials_dir)

    print("=" * 50)
    print("Googleカレンダー空き時間検索アプリ")
    print("=" * 50)
    print()
    print("サーバーを起動しています...")
    print("ブラウザで http://localhost:5000 にアクセスしてください")
    print()
    print("初回起動時は credentials/credentials.json を")
    print("Google Cloud Console からダウンロードして配置してください")
    print("=" * 50)

    app.run(debug=True, port=5000)
