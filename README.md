# VTP Panel Edition

**VTP** نسخه پنل‌دار و به‌روزشده VortexL2 برای ساخت و مدیریت Tunnel با EasyTier است. هدف این نسخه این است که بعد از نصب، پنل گرافیکی به‌صورت خودکار بالا بیاید و کاربر برای ساخت Tunnel، Start/Stop، Port Forwarding و مشاهده وضعیت نیازی به اجرای کامندهای دستی نداشته باشد.

Repository owner: `Unknown-sir`  
Repository name: `VTP`


## تغییر مهم نسخه 4.4.0

در نسخه `4.4.0-vtp` رفتار دکمه **ذخیره و اجرا** اصلاح شده است:

- هنگام کلیک روی دکمه، متن دکمه به «در حال ذخیره و اجرا...» تغییر می‌کند.
- ابتدا فایل کانفیگ Tunnel در `/etc/vortexl2/tunnels/` ذخیره می‌شود.
- بعد از ذخیره، سرویس systemd همان Tunnel ساخته و اجرا می‌شود.
- اگر EasyTier، systemd یا HAProxy خطا بدهند، کانفیگ حذف نمی‌شود و Tunnel در بخش **مدیریت Tunnelها** نمایش داده می‌شود.
- نتیجه کامل عملیات داخل همان مرحله آخر Wizard نیز نمایش داده می‌شود.

این تغییر باعث می‌شود اگر اجرای سرویس به‌خاطر نصب نبودن EasyTier یا خطای سیستم ناموفق باشد، کاربر باز هم Tunnel ساخته‌شده را ببیند، لاگ را بررسی کند و بعد از رفع مشکل دوباره Start بزند.

## قابلیت‌های اصلی

- پنل وب گرافیکی با طراحی مرحله‌به‌مرحله و بخش‌بندی‌شده
- اجرای خودکار پنل بعد از نصب با systemd
- ساخت Tunnel طبق مراحل اصلی اسکریپت VortexL2:
  1. انتخاب نقش `IRAN` یا `KHAREJ`
  2. تنظیم IP داخلی Tunnel، پورت، Secret و RPC Port
  3. وارد کردن Public IP سمت مقابل به‌عنوان Peer
  4. ذخیره کانفیگ و اجرای سرویس با دکمه **ذخیره و اجرا**
- دکمه نهایی Wizard همزمان این کارها را انجام می‌دهد:
  - ذخیره فایل Tunnel در `/etc/vortexl2/tunnels/`
  - ساخت یا بروزرسانی systemd service همان Tunnel
  - اجرای سرویس EasyTier
  - اعمال HAProxy در صورت فعال بودن Forwarding
- رفع مشکل اجرا نشدن Tunnel دوم روی یک سرور
- یکتا شدن خودکار مقدارهای زیر برای هر Tunnel روی یک سرور:
  - `interface_name`
  - `local_ip`
  - `listen port`
  - `rpc_port`
  - `hostname`
- پشتیبانی از چند Peer برای سناریوی یک سرور خارج به چند سرور ایران
- سازگاری با کانفیگ قدیمی `peer_ip`
- نصب خودکار EasyTier در زمان نصب پروژه
- دکمه نصب EasyTier داخل پنل، برای زمانی که نصب خودکار به‌دلیل محدودیت شبکه انجام نشده باشد
- مدیریت Start / Stop / Restart / Delete از داخل پنل
- مشاهده لاگ هر Tunnel از داخل پنل
- مدیریت Peerها از داخل پنل
- مدیریت Port Forwarding با HAProxy
- جلوگیری از خطای HAProxy در حالت بدون listener
- ابزار عیب‌یابی `vtp-doctor`

## پیش‌نیازها

سیستم پیشنهادی:

- Ubuntu 20.04 / 22.04 / 24.04
- Debian 11 / 12
- دسترسی root
- systemd
- دسترسی اینترنت برای نصب پکیج‌ها و EasyTier

پورت‌های پیش‌فرض:

| سرویس | پورت | توضیح |
|---|---:|---|
| VTP Panel | `8088/tcp` | پنل گرافیکی |
| EasyTier Tunnel 1 | `2070/tcp` | Listener تونل اول |
| EasyTier Tunnel 2 | `2071/tcp` | اگر روی همان سرور تونل دوم بسازید، خودکار یکتا می‌شود |
| RPC Tunnel 1 | `15888/tcp` روی localhost | کنترل EasyTier |
| RPC Tunnel 2 | `15889/tcp` روی localhost | RPC تونل دوم |

## نصب سریع از GitHub

```bash
bash <(curl -Ls https://raw.githubusercontent.com/Unknown-sir/VTP/main/install.sh)
```

## نصب از فایل ZIP

```bash
unzip VTP-Panel-Edition.zip
cd VTP
sudo bash install.sh
```

بعد از نصب، خروجی شبیه این نمایش داده می‌شود:

```text
Panel URL:  http://SERVER_IP:8088
Local URL:  http://127.0.0.1:8088
Token:      xxxxx
Doctor:     sudo vtp-doctor
CLI:        sudo vtp status
```

Token پنل در این مسیر ذخیره می‌شود:

```bash
sudo cat /etc/vortexl2/panel_token
```

## ورود به پنل

در مرورگر باز کنید:

```text
http://SERVER_IP:8088
```

سپس Token را وارد کنید.

بخش‌های پنل:

1. وضعیت کلی
2. ساخت Tunnel مرحله‌ای
3. مدیریت Tunnelها
4. Port Forwarding
5. عیب‌یابی و لاگ

## مراحل ساخت Tunnel مطابق اسکریپت

### سناریوی IRAN

در پنل وارد بخش **ساخت Tunnel مرحله‌ای** شوید و گزینه **IRAN** را انتخاب کنید.

مقادیر پیش‌فرض مطابق اسکریپت:

```text
Role: IRAN
Tunnel IP: 10.155.155.1
Hostname: iran
Port: 2070
Secret: vortexl2
Peer: KHAREJ_PUBLIC_IP:2070
Remote Forward IP: 10.155.155.2
```

در مرحله Peer باید Public IP سرور خارج را وارد کنید:

```text
KHAREJ_PUBLIC_IP:2070 # kharej
```

در مرحله آخر روی **ذخیره و اجرا** بزنید. پنل کانفیگ را ذخیره می‌کند، سرویس systemd تونل را می‌سازد و همان لحظه آن را اجرا می‌کند.

### سناریوی KHAREJ

در پنل وارد بخش **ساخت Tunnel مرحله‌ای** شوید و گزینه **KHAREJ** را انتخاب کنید.

مقادیر پیش‌فرض مطابق اسکریپت:

```text
Role: KHAREJ
Tunnel IP: 10.155.155.2
Hostname: kharej
Port: 2070
Secret: vortexl2
Peer: IRAN_PUBLIC_IP:2070
Remote Forward IP: 10.155.155.1
```

در مرحله Peer باید Public IP سرور ایران را وارد کنید:

```text
IRAN_PUBLIC_IP:2070 # iran
```

در مرحله آخر روی **ذخیره و اجرا** بزنید.

## سناریوی یک خارج به چند ایران

برای چند سرور ایران، روی سرور خارج در مرحله Peer می‌توانید چند IP عمومی ایران وارد کنید؛ هر Peer باید در یک خط باشد:

```text
IRAN1_PUBLIC_IP:2070 # iran1
IRAN2_PUBLIC_IP:2070 # iran2
IRAN3_PUBLIC_IP:2070 # iran3
```

روی هر سرور ایران، فقط IP عمومی سرور خارج را به‌عنوان Peer وارد کنید:

```text
KHAREJ_PUBLIC_IP:2070 # kharej
```

Secret همه سرورها باید یکسان باشد.

## دلیل رفع مشکل Tunnel دوم

در نسخه‌های قبلی، Tunnel دوم ممکن بود اجرا نشود چون چند مقدار ثابت تکرار می‌شدند:

```text
tun1
2070
15888
10.155.155.1
node1
```

در این نسخه قبل از ساخت سرویس، conflict بررسی می‌شود و برای Tunnelهای بعدی مقدارهای آزاد ساخته می‌شود:

```text
tunnel1:
  interface_name: tun1
  port: 2070
  rpc_port: 15888

tunnel2:
  interface_name: tun2
  port: 2071
  rpc_port: 15889
```

## EasyTier نصب نشد یا داخل پنل نوشته شد not found

اگر داخل پنل در بخش وضعیت کلی نوشته شد:

```text
EasyTier: not found
```

از همان بخش روی **نصب خودکار EasyTier** کلیک کنید.

بررسی وضعیت:

```bash
sudo vtp-doctor
sudo vtp status
```

## Port Forwarding با HAProxy

برای فعال کردن HAProxy باید حداقل روی یک Tunnel مقدارهای زیر تعریف شده باشد:

- `Remote Forward IP`
- `Forwarded ports`

مثال:

```text
Remote Forward IP: 10.155.155.2
Forwarded ports: 80,443,2087
```

سپس در بخش **Port Forwarding** روی **فعال‌سازی HAProxy** کلیک کنید.

اگر هنوز هیچ Forwarded Port تعریف نشده باشد، HAProxy دیگر با خطای زیر متوقف نمی‌شود:

```text
Configuration file has no error but will not start (no listener)
```

در این حالت پنل پیام واضح می‌دهد که HAProxy آماده است، اما چون listener وجود ندارد اجرا نمی‌شود. بعد از تعریف پورت، HAProxy به‌صورت عادی Start می‌شود.

## مسیر فایل‌ها

```text
/opt/vortexl2                         فایل‌های برنامه
/etc/vortexl2/config.yaml             تنظیمات کلی
/etc/vortexl2/panel_token             توکن ورود پنل
/etc/vortexl2/tunnels/*.yaml          تنظیمات Tunnelها
/etc/systemd/system/vortexl2-panel.service
/etc/systemd/system/vortexl2-forward-daemon.service
/etc/systemd/system/vortexl2-easytier-*.service
```

## سرویس‌های systemd

وضعیت پنل:

```bash
sudo systemctl status vortexl2-panel
```

ری‌استارت پنل:

```bash
sudo systemctl restart vortexl2-panel
```

وضعیت سرویس‌های EasyTier ساخته‌شده:

```bash
sudo systemctl status 'vortexl2-easytier-*'
```

لاگ پنل:

```bash
sudo journalctl -u vortexl2-panel -f
```

لاگ Tunnelها:

```bash
sudo journalctl -u 'vortexl2-easytier-*' -f
```

## CLI اختیاری

کار اصلی از پنل انجام می‌شود، اما این دستورها هم وجود دارند:

```bash
sudo vtp status
sudo vtp apply
sudo vtp panel --host 0.0.0.0 --port 8088
sudo vtp forward-mode haproxy
sudo vtp-doctor
```

## امنیت پنل

پنل با Token محافظت می‌شود، ولی بهتر است پورت پنل را فقط برای IPهای مورد اعتماد باز کنید.

نمونه با UFW:

```bash
sudo ufw allow from YOUR_IP to any port 8088 proto tcp
```

یا پنل را فقط از طریق SSH Tunnel باز کنید:

```bash
ssh -L 8088:127.0.0.1:8088 root@SERVER_IP
```

سپس در مرورگر سیستم خودتان باز کنید:

```text
http://127.0.0.1:8088
```

## حذف پروژه

```bash
sudo bash uninstall.sh
```

## عیب‌یابی سریع

```bash
sudo vtp-doctor
sudo systemctl status vortexl2-panel
sudo journalctl -u vortexl2-panel -n 100 --no-pager
sudo journalctl -u 'vortexl2-easytier-*' -n 100 --no-pager
```

اگر Tunnel اجرا نشد، معمولاً یکی از این موارد علت است:

- EasyTier نصب نشده است
- پورت EasyTier روی فایروال بسته است
- Secret بین سرورها یکسان نیست
- IP داخلی Tunnel تکراری است
- Peer اشتباه وارد شده است
- پورت Listener یا RPC با سرویس دیگری conflict دارد
