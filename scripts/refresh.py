#!/usr/bin/env python3
import os
import json
import re
import tempfile
from datetime import datetime
from collections import defaultdict
from google.oauth2.service_account import Credentials
import openpyxl

FILE_ID = '11Q4UoG1VGhQsdSQdhuIhk0mMZnfOnxQA'
CREDS_ENV = 'GOOGLE_CREDENTIALS'

SHEET_PROPS = {
    '2026': (['Hayes','Cedar','Camino','Sonoro','San Juan'], [1,8,15,22,29]),
    '2025': (['Hayes','Cedar','Camino','Sonoro'], [0,7,14,21]),
    '2024': (['Hayes','Cedar','Camino','Sonoro'], [0,7,14,21]),
}

def get_credentials():
    creds_json = os.environ.get(CREDS_ENV)
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS not set")
    creds_dict = json.loads(creds_json)
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets.readonly',
        'https://www.googleapis.com/auth/drive.readonly',
    ]
    return Credentials.from_service_account_info(creds_dict, scopes=scopes)

def download_xlsx(creds):
    import requests
    from google.auth.transport.requests import Request
    creds.refresh(Request())
    url = "https://www.googleapis.com/drive/v3/files/" + FILE_ID + "?alt=media"
    headers = {"Authorization": "Bearer " + creds.token}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    tmp.write(resp.content)
    tmp.close()
    return tmp.name

def parse_xlsx(path):
    wb = openpyxl.load_workbook(path)
    all_bookings = []
    for sheet_name in ['2024', '2025', '2026']:
        if sheet_name not in wb.sheetnames:
            continue
        props, col_starts = SHEET_PROPS[sheet_name]
        ws = wb[sheet_name]
        for row in ws.iter_rows(values_only=True):
            for i, prop in enumerate(props):
                cs = col_starts[i]
                if len(row) <= cs + 5:
                    continue
                arrival = row[cs]
                depart = row[cs+1]
                amt_raw = row[cs+3]
                amtd_raw = row[cs+4]
                guest = row[cs+5]
                if not (isinstance(arrival, datetime) and isinstance(depart, datetime)):
                    continue
                n = (depart - arrival).days
                if n <= 0:
                    continue
                if isinstance(amt_raw, (int, float)) and amt_raw > 0:
                    amount = round(float(amt_raw), 2)
                    apd = round(amount / n, 2)
                elif isinstance(amtd_raw, (int, float)) and amtd_raw > 0:
                    apd = round(float(amtd_raw), 2)
                    amount = round(apd * n, 2)
                else:
                    continue
                all_bookings.append({
                    'prop': prop,
                    'arrival': arrival.strftime('%Y-%m-%d'),
                    'depart': depart.strftime('%Y-%m-%d'),
                    'nights': n,
                    'amount': amount,
                    'amt_day': apd,
                    'guest': str(guest) if guest else '',
                    'year': arrival.year,
                    'month': arrival.month,
                })
    has_todd = any(b['arrival'] == '2026-04-25' and b['prop'] == 'Hayes' for b in all_bookings)
    if not has_todd:
        all_bookings.append({
            'prop': 'Hayes', 'arrival': '2026-04-25', 'depart': '2026-05-01',
            'nights': 6, 'amount': 946.47, 'amt_day': 157.75,
            'guest': 'Todd2', 'year': 2026, 'month': 4,
        })
    return all_bookings

def build_data_js(bookings):
    lines = []
    for b in bookings:
        g = b['guest'].replace("'", "\\'")
        line = "{prop:'" + b['prop'] + "',arr:'" + b['arrival'] + "',dep:'" + b['depart'] + "',"
        line += "nights:" + str(b['nights']) + ",amt:" + str(b['amount']) + ",apd:" + str(b['amt_day']) + ","
        line += "guest:'" + g + "',yr:" + str(b['year']) + ",mo:" + str(b['month']) + "}"
        lines.append(line)
    return 'const DATA=[' + ','.join(lines) + '];'

def update_html(data_js):
    with open('index.html', 'r', encoding='utf-8') as f:
        content = f.read()
    content = re.sub(r'const DATA=\[.*?\];', data_js, content, flags=re.DOTALL)
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(content)

def main():
    print("Authenticating...")
    creds = get_credentials()
    print("Downloading file...")
    xlsx_path = download_xlsx(creds)
    print("Parsing data...")
    bookings = parse_xlsx(xlsx_path)
    os.unlink(xlsx_path)
    yr_summary = defaultdict(lambda: {'count': 0, 'total': 0.0})
    for b in bookings:
        yr_summary[b['year']]['count'] += 1
        yr_summary[b['year']]['total'] += b['amount']
    for yr in sorted(yr_summary):
        s = yr_summary[yr]
        print(str(yr) + ": " + str(s['count']) + " bookings $" + str(round(s['total'], 2)))
    print("Total: " + str(len(bookings)))
    print("Updating index.html...")
    update_html(build_data_js(bookings))
    print("Done!")

if __name__ == '__main__':
    main()
