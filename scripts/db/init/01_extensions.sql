-- 최초 기동 시 1회 실행 (docker-entrypoint-initdb.d).
-- 🚨 이미 만들어진 볼륨에는 실행되지 않는다. 그래서 launcher db-up 이
--    매번 CREATE EXTENSION IF NOT EXISTS 를 한 번 더 던진다.
CREATE EXTENSION IF NOT EXISTS vector;
