import requests

def get_market_status():
    try:
        arr = requests.get('http://qt.gtimg.cn/q=sh000001', timeout=1).text.split('~')
        return {
            'status': 'trading',
            'status_desc': '实时行情',
            'sentiment_level': 'normal',
            'sentiment_desc': '',
            'show_nuclear': False,
            'index_point': float(arr[3]),
            'index_change': float(arr[31]),
            'is_thunder_time': False,
            'is_tail_time': False
        }
    except:
        return {
            'status': 'trading',
            'status_desc': '获取失败',
            'sentiment_level': 'unknown',
            'sentiment_desc': '',
            'show_nuclear': False,
            'index_point': 0,
            'index_change': 0,
            'is_thunder_time': False,
            'is_tail_time': False
        }
