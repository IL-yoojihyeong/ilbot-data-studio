# IL-BOT Data Studio — 배포

로봇 데이터 수집·레이블링 플랫폼을 서버에 설치하는 배포 저장소입니다.
플랫폼은 컨테이너 이미지로, 수집 프로그램은 소스에서 설치합니다.

## 구성

- **플랫폼** (워크스테이션 1대): Docker 컨테이너 1개 + 데이터 폴더 1개. 웹 UI 제공.
- **수집 브리지** (노트북): 로봇과 유선 직결해 데이터를 녹화, 플랫폼으로 업로드
- 
## 빠른 시작

전체 절차는 [INSTALL.md](INSTALL.md), 설정값은 그 안의 **설정 표**를 참고하세요.

```bash
# 1) 플랫폼 (워크스테이션)
git clone https://github.com/IL-yoojihyeong/ilbot-data-studio.git
cd ilbot-data-studio
cp .env.example .env          # ROBOLABEL_PASSWORD, STUDIO_DATA_DIR 등 수정
docker compose up -d --build  # 소스로 이미지 빌드 + 실행
#   → 브라우저에서 http://<이 서버 IP>:8322

# 2) 노트북 (수집 프로그램) — 레포 하나만 clone
git clone https://github.com/IL-yoojihyeong/ilbot-collector.git
cd ilbot-collector && ./install.sh
./run_gui.sh                  # 첫 실행 시 설정 창이 떠서 주소·계정 입력
```

## 업데이트

[UPDATE.md](UPDATE.md) — 새 버전으로 올릴 때 데이터·설정은 보존됩니다.
