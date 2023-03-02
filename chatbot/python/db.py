import redis
r = redis.Redis(host='47.103.17.145', port=8010, db=0, password='godword')
r.set('foo', 'bar')
print(r.get('foo'))
