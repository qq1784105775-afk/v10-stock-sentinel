import requests

def get_price(code):
    c = code.lower()
    if c.endswith('.sz'):
        c = 'sz' + c[:6]
    elif c.endswith('.sh'):
        c = 'sh' + c[:6]
    else:
        c = code

    try:
        r = requests.get(f'http://qt.gtimg.cn/q={c}', timeout=1).text.split('~')
        return {
            'name': r[1],
            'price': float(r[3]),
            'yclose': float(r[4])
        }
    except:
        return {'name': code, 'price': 0, 'yclose': 0}
