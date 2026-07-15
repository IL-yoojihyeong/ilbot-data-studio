# 업데이트 절차

데이터(`STUDIO_DATA_DIR` 폴더)와 설정(`.env`, 노트북 `config.json`)은 그대로 보존됩니다.

## 플랫폼 (워크스테이션)

```bash
cd ilbot-data-studio
git pull
docker compose up -d --build     # 새 소스로 재빌드 + 재기동
```

- DB 스키마 변경은 서버 기동 시 자동 마이그레이션됩니다(기존 데이터 유지).
- 롤백: `git checkout <이전 커밋/태그>` 후 다시 `docker compose up -d --build`.

## 노트북 (수집 프로그램)

```bash
cd ilbot-collector
git pull && ./install.sh         # config.json은 그대로 유지됨
```

## 백업 (업데이트 전 권장)

```bash
tar czf ilbot-backup-$(date +%Y%m%d).tar.gz -C <STUDIO_DATA_DIR 상위> <폴더명>
```
