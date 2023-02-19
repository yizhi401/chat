import requests

url = "https://api.writesonic.com/v2/business/content/chatsonic?engine=premium&language=zh"
proxies = { 'http': 'http://127.0.0.1:33210', 'https': 'http://127.0.0.1:33210', }

payload = {
    "enable_google_results": "true",
    "enable_memory": False,
    "input_text": "华为公司怎么样？"
}
headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "X-API-KEY": "7eaae20d-c54f-4eba-bbfd-eae8d39fd6d3"
}

response = requests.post(url, json=payload, headers=headers, proxies=proxies, verify=False)

print(response.text)