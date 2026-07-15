# IL-BOT Data Studio 설치 가이드 

- 플랫폼: **현재 레포** (`ilbot-data-studio`)
- 수집 프로그램: [`ilbot-collector`](https://github.com/IL-yoojihyeong/ilbot-collector)

## 0. requirements

| 항목 | 확인 내용 |
|---|---|
| 워크스테이션 | OS(리눅스 권장) / Docker 설치 / 디스크 용량 (에피소드당 ~150MB) |
| 노트북 | Ubuntu 22.04+ / 유선 랜 포트(로봇 직결) |

## 1. 설정 레퍼런스 —

환경에 맞게 **아래 값만** 설정하면 됩니다. 

| 값 | 어디서 설정 | 기본값 / 비고 |
|---|---|---|
| 플랫폼 접속 비밀번호 | 워크스테이션 `.env` → `ROBOLABEL_PASSWORD` | 필수. 수집 프로그램 설정과 동일하게 |
| 플랫폼 포트 | `.env` → `STUDIO_PORT` | 8322 |
| **플랫폼 데이터 저장위치** | `.env` → `STUDIO_DATA_DIR` | `./data`. 예: `/mnt/data/ilbot` |
| 수집 프로그램 → 플랫폼 주소·계정 | 노트북 **GUI [⚙ 설정] 창** | `http://<서버 IP>:8322` + 위 비밀번호 |
| 로봇 IP·비밀번호 | 노트북 GUI [⚙ 설정] 창 | IP `10.42.1.101`(고정). 노트북 유선 IP만 `10.42.1.102/24`로 수동 설정 |
| 로컬 저장 모드 위치 | GUI [저장위치 변경] 버튼 | `~/ilbot_data` |

> **노트북 설정은 GUI 프로그램 설정 창의 4칸이 전부입니다.** 

## 2. 플랫폼 설치 

```bash
docker --version                       
git clone https://github.com/IL-yoojihyeong/ilbot-data-studio.git
cd ilbot-data-studio
cp .env.example .env                   # 위 표 참고해 수정 (비밀번호·데이터 위치 필수)
docker compose up -d --build           
curl -u admin:<비밀번호> http://localhost:8322/api/projects   
```

브라우저에서 `http://<워크스테이션 IP>:8322` → 우측 상단 프로필 선택(User Center에서 생성) →
Project Center에서 프로젝트 생성.

- 데이터 전체가 `STUDIO_DATA_DIR` 폴더 하나에 저장됨 → 백업 = 이 폴더 복사
- 로그: `docker logs ilbot-data-studio`

## 3. 노트북(수집 프로그램) 설치 

```bash
git clone https://github.com/IL-yoojihyeong/ilbot-collector.git
cd ilbot-collector && ./install.sh
sudo apt install -y libxcb-cursor0    # PyQt6 런타임 (한 번만)
./run_gui.sh
```

상세 절차는 [ilbot-collector의 INSTALL.md](https://github.com/IL-yoojihyeong/ilbot-collector/blob/main/INSTALL.md) 참고.

첫 실행 시 **설정 창**이 자동으로 뜹니다 → 플랫폼 주소·계정, 로봇 IP·비밀번호 입력 →
[연결 테스트]로 확인 → 저장. 이후:

1. 노트북 유선 IP를 `10.42.1.102/24`로 설정, 로봇과 직결
2. `.venv/bin/python scripts/preflight_robot.py` — 로봇/GDK/카메라 사전 점검
3. GUI에서 워밍업 → 프로젝트·Job(또는 로컬 데이터셋) 선택 → 녹화
4. 서버 모드는 자동 업로드·변환, 로컬 모드는 노트북에 LeRobot로 바로 저장

## 4. 네트워크

- **기본(권장)**: 노트북·워크스테이션이 같은 사내 LAN — 추가 구성 없음.
  워크스테이션에 고정 IP(또는 사내 DNS 이름)를 부여하세요.
- **원격 접근이 필요할 때**: [Tailscale](https://tailscale.com) — **귀사 명의 tailnet**을 만들어
  워크스테이션·노트북을 가입시키면 어디서든 접속됩니다(무료 플랜으로 시작 가능).
  수집 프로그램 설정의 플랫폼 주소를 Tailscale IP(100.x.x.x)로 넣으면 됩니다.
