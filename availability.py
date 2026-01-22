"""
空き時間計算ロジック
2つのカレンダーの予定を統合し、共通の空き時間を抽出
"""

from datetime import datetime, timedelta, time
from dateutil import parser as date_parser
import re
import calendar as cal


# デフォルト設定
DEFAULT_BUFFER_MINUTES = 30  # 予定終了後のバッファ時間
DEFAULT_SLOT_DURATION = 60  # 候補の時間枠（分）
DEFAULT_MAX_CANDIDATES = 5  # 最大候補数
DEFAULT_WORK_START = time(9, 0)  # 営業開始時間
DEFAULT_WORK_END = time(18, 0)  # 営業終了時間


def merge_busy_periods(events_list, buffer_minutes=DEFAULT_BUFFER_MINUTES):
    """
    複数アカウントの予定を統合し、ビジー期間をマージ

    Args:
        events_list: 各アカウントの予定リスト [[events1], [events2], ...]
        buffer_minutes: 予定終了後のバッファ時間（分）

    Returns:
        list: マージされたビジー期間 [{'start': datetime, 'end': datetime}, ...]
    """
    # 全予定を結合
    all_busy = []
    for events in events_list:
        for event in events:
            if isinstance(event, dict) and 'error' not in event:
                start = event['start']
                # バッファを追加した終了時間
                end = event['end'] + timedelta(minutes=buffer_minutes)

                # 終日イベントの場合
                if event.get('all_day'):
                    # 終日イベントは日付のみなので、時刻を設定
                    if isinstance(start, datetime) and start.hour == 0 and start.minute == 0:
                        pass  # そのまま使用
                    else:
                        start = datetime.combine(start.date() if hasattr(start, 'date') else start, time(0, 0))
                        end = datetime.combine(event['end'].date() if hasattr(event['end'], 'date') else event['end'], time(23, 59))

                all_busy.append({'start': start, 'end': end})

    if not all_busy:
        return []

    # 開始時間でソート
    all_busy.sort(key=lambda x: x['start'])

    # 重複する期間をマージ
    merged = [all_busy[0]]
    for current in all_busy[1:]:
        last = merged[-1]
        # naive/aware datetime の統一
        current_start = current['start']
        current_end = current['end']
        last_end = last['end']

        # タイムゾーン情報を削除して比較
        if hasattr(current_start, 'replace'):
            current_start_naive = current_start.replace(tzinfo=None) if current_start.tzinfo else current_start
            current_end_naive = current_end.replace(tzinfo=None) if current_end.tzinfo else current_end
            last_end_naive = last_end.replace(tzinfo=None) if last_end.tzinfo else last_end
        else:
            current_start_naive = current_start
            current_end_naive = current_end
            last_end_naive = last_end

        if current_start_naive <= last_end_naive:
            # 重複または連続しているのでマージ
            if current_end_naive > last_end_naive:
                last['end'] = current['end']
        else:
            merged.append(current)

    return merged


def find_free_slots(time_min, time_max, busy_periods, slot_duration=DEFAULT_SLOT_DURATION,
                    work_start=DEFAULT_WORK_START, work_end=DEFAULT_WORK_END):
    """
    空き時間スロットを検索

    Args:
        time_min: 検索開始日時
        time_max: 検索終了日時
        busy_periods: ビジー期間のリスト
        slot_duration: スロットの長さ（分）
        work_start: 営業開始時間
        work_end: 営業終了時間

    Returns:
        list: 空き時間スロット [{'start': datetime, 'end': datetime}, ...]
    """
    free_slots = []

    # タイムゾーン情報を削除
    time_min = time_min.replace(tzinfo=None) if time_min.tzinfo else time_min
    time_max = time_max.replace(tzinfo=None) if time_max.tzinfo else time_max

    # 日付ごとに処理
    current_date = time_min.date()
    end_date = time_max.date()

    while current_date <= end_date:
        # 週末はスキップ
        if current_date.weekday() >= 5:  # 土曜=5, 日曜=6
            current_date += timedelta(days=1)
            continue

        # この日の営業時間
        day_start = datetime.combine(current_date, work_start)
        day_end = datetime.combine(current_date, work_end)

        # 検索範囲で制限
        if day_start < time_min:
            day_start = time_min
        if day_end > time_max:
            day_end = time_max

        if day_start >= day_end:
            current_date += timedelta(days=1)
            continue

        # この日のビジー期間を取得
        day_busy = []
        for busy in busy_periods:
            busy_start = busy['start'].replace(tzinfo=None) if busy['start'].tzinfo else busy['start']
            busy_end = busy['end'].replace(tzinfo=None) if busy['end'].tzinfo else busy['end']

            # この日と重なる部分があるか
            if busy_start.date() <= current_date <= busy_end.date():
                overlap_start = max(busy_start, day_start)
                overlap_end = min(busy_end, day_end)
                if overlap_start < overlap_end:
                    day_busy.append({'start': overlap_start, 'end': overlap_end})

        # ビジー期間をソート
        day_busy.sort(key=lambda x: x['start'])

        # 空き時間を計算
        current_time = day_start
        for busy in day_busy:
            if current_time < busy['start']:
                # ビジー開始前に空き時間がある
                free_start = current_time
                free_end = busy['start']
                # スロット単位で分割
                slots = split_into_slots(free_start, free_end, slot_duration)
                free_slots.extend(slots)
            current_time = max(current_time, busy['end'])

        # 最後のビジー後の空き時間
        if current_time < day_end:
            slots = split_into_slots(current_time, day_end, slot_duration)
            free_slots.extend(slots)

        current_date += timedelta(days=1)

    return free_slots


def split_into_slots(start, end, slot_duration):
    """
    期間をスロット単位に分割

    Args:
        start: 開始時間
        end: 終了時間
        slot_duration: スロットの長さ（分）

    Returns:
        list: スロットのリスト
    """
    slots = []
    current = start
    slot_delta = timedelta(minutes=slot_duration)

    while current + slot_delta <= end:
        slots.append({
            'start': current,
            'end': current + slot_delta
        })
        current += slot_delta

    return slots


def find_available_slots(events_by_account, time_min, time_max,
                        buffer_minutes=DEFAULT_BUFFER_MINUTES,
                        slot_duration=DEFAULT_SLOT_DURATION,
                        max_candidates=DEFAULT_MAX_CANDIDATES,
                        work_start=DEFAULT_WORK_START,
                        work_end=DEFAULT_WORK_END):
    """
    空き時間候補を検索するメイン関数

    Args:
        events_by_account: アカウントごとの予定 {account_id: [events], ...}
        time_min: 検索開始日時
        time_max: 検索終了日時
        buffer_minutes: 予定終了後のバッファ（分）
        slot_duration: スロットの長さ（分）
        max_candidates: 最大候補数
        work_start: 営業開始時間
        work_end: 営業終了時間

    Returns:
        list: 空き時間候補
    """
    # 全アカウントの予定を取得
    events_list = []
    for account_id, events in events_by_account.items():
        if isinstance(events, list):
            events_list.append(events)
        elif isinstance(events, dict) and 'error' in events:
            # 認証エラーなどの場合はスキップしない
            raise ValueError(events['error'])

    # ビジー期間をマージ
    busy_periods = merge_busy_periods(events_list, buffer_minutes)

    # 空きスロットを検索
    free_slots = find_free_slots(
        time_min, time_max, busy_periods,
        slot_duration=slot_duration,
        work_start=work_start,
        work_end=work_end
    )

    # 最大候補数で制限
    return free_slots[:max_candidates]


def format_slot(slot):
    """
    スロットをフォーマットして表示用文字列に変換

    Args:
        slot: {'start': datetime, 'end': datetime}

    Returns:
        str: フォーマットされた文字列
    """
    start = slot['start']
    end = slot['end']

    # 曜日の日本語表記
    weekdays = ['月', '火', '水', '木', '金', '土', '日']
    weekday = weekdays[start.weekday()]

    return f"{start.month}/{start.day}（{weekday}） {start.strftime('%H:%M')}–{end.strftime('%H:%M')}"


def format_candidates(slots):
    """
    候補リストをフォーマット

    Args:
        slots: スロットのリスト

    Returns:
        str: フォーマットされた候補リスト
    """
    if not slots:
        return "該当する空き時間が見つかりませんでした。"

    lines = ["候補日"]
    for slot in slots:
        lines.append(f"・{format_slot(slot)}")

    return "\n".join(lines)


# 日本語の日付・時間解析

def parse_date_query(query, base_date=None):
    """
    自然言語の日付クエリを解析

    Args:
        query: 入力文字列
        base_date: 基準日（デフォルト: 今日）

    Returns:
        dict: {
            'start_date': datetime,
            'end_date': datetime,
            'slot_duration': int (分),
            'work_start': time,
            'work_end': time,
            'max_candidates': int
        }
    """
    if base_date is None:
        base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    result = {
        'start_date': base_date,
        'end_date': base_date + timedelta(days=7),
        'slot_duration': DEFAULT_SLOT_DURATION,
        'work_start': DEFAULT_WORK_START,
        'work_end': DEFAULT_WORK_END,
        'max_candidates': DEFAULT_MAX_CANDIDATES
    }

    query = query.lower()

    # 「今週」の解析
    if '今週' in query:
        # 今週の月曜日から日曜日
        days_since_monday = base_date.weekday()
        monday = base_date - timedelta(days=days_since_monday)
        sunday = monday + timedelta(days=6)
        result['start_date'] = monday
        result['end_date'] = sunday

    # 「来週」の解析
    elif '来週' in query:
        days_until_monday = 7 - base_date.weekday()
        if base_date.weekday() == 0:  # 今日が月曜日
            days_until_monday = 7
        next_monday = base_date + timedelta(days=days_until_monday)
        next_sunday = next_monday + timedelta(days=6)
        result['start_date'] = next_monday
        result['end_date'] = next_sunday

    # 「今日」の解析
    elif '今日' in query:
        result['start_date'] = base_date
        result['end_date'] = base_date + timedelta(days=1)

    # 「明日」の解析
    elif '明日' in query:
        tomorrow = base_date + timedelta(days=1)
        result['start_date'] = tomorrow
        result['end_date'] = tomorrow + timedelta(days=1)

    # 「〇日」または「〇月〇日」の解析
    month_day_match = re.search(r'(\d{1,2})月(\d{1,2})日', query)
    day_only_match = re.search(r'(\d{1,2})日', query)

    if month_day_match:
        month = int(month_day_match.group(1))
        day = int(month_day_match.group(2))
        year = base_date.year
        # 過去の日付の場合は来年
        target_date = datetime(year, month, day)
        if target_date < base_date:
            target_date = datetime(year + 1, month, day)
        result['start_date'] = target_date
        result['end_date'] = target_date + timedelta(days=1)
    elif day_only_match and '月' not in query[:query.find('日')]:
        day = int(day_only_match.group(1))
        year = base_date.year
        month = base_date.month
        try:
            target_date = datetime(year, month, day)
            if target_date < base_date:
                # 来月に調整
                if month == 12:
                    target_date = datetime(year + 1, 1, day)
                else:
                    target_date = datetime(year, month + 1, day)
            result['start_date'] = target_date
            result['end_date'] = target_date + timedelta(days=1)
        except ValueError:
            pass  # 無効な日付

    # 「午前」「午後」の解析
    if '午前' in query:
        result['work_start'] = time(9, 0)
        result['work_end'] = time(12, 0)
    elif '午後' in query:
        result['work_start'] = time(13, 0)
        result['work_end'] = time(18, 0)

    # 特定の時間の解析 (例: 14時以降, 10時から)
    time_from_match = re.search(r'(\d{1,2})時(以降|から|〜)', query)
    time_to_match = re.search(r'(\d{1,2})時(まで|以前)', query)

    if time_from_match:
        hour = int(time_from_match.group(1))
        if 0 <= hour <= 23:
            result['work_start'] = time(hour, 0)

    if time_to_match:
        hour = int(time_to_match.group(1))
        if 0 <= hour <= 23:
            result['work_end'] = time(hour, 0)

    # 時間枠の解析 (例: 30分, 2時間)
    duration_match = re.search(r'(\d+)(分|時間)(枠|単位)?', query)
    if duration_match:
        value = int(duration_match.group(1))
        unit = duration_match.group(2)
        if unit == '時間':
            result['slot_duration'] = value * 60
        else:
            result['slot_duration'] = value

    # 候補数の解析 (例: 3件, 10個)
    count_match = re.search(r'(\d+)(件|個|つ)', query)
    if count_match:
        result['max_candidates'] = int(count_match.group(1))

    return result
