# VTP Panel Edition

**VTP** نسخه پنل‌دار VortexL2 برای ساخت و مدیریت Tunnel با EasyTier است. هدف این نسخه این است که کاربر بعد از نصب، از طریق یک پنل گرافیکی مرحله‌به‌مرحله Tunnel بسازد و دیگر برای عملیات معمول نیازی به اجرای کامند نداشته باشد.

این نسخه برای سناریوی رایج زیر آماده شده است:

```text
یک سرور خارج / Hub
 ├── اتصال به ایران 1
 ├── اتصال به ایران 2
 └── اتصال به ایران‌های بیشتر
```

## قابلیت‌های اصلی

- پنل وب گرافیکی با طراحی بخش‌بندی‌شده و مرحله‌به‌مرحله
- اجرای خودکار پنل بعد از نصب با systemd
- نصب خودکار EasyTier در زمان نصب پروژه
- دکمه نصب EasyTier داخل خود پنل، برای زمانی که نصب خودکار به‌دلیل محدودیت شبکه انجام نشده باشد
- رفع مشکل اجرای هم‌زمان چند Tunnel EasyTier روی یک سرور
- ایجاد خودکار مقدارهای یکتا برای هر Tunnel:
  - `interface_name`
  - `local_ip`
  - `listen port`
  - `rpc_port`
  - `hostname`
- پشتیبانی از چند Peer در یک Tunnel با ساختار `peers: []`
- سازگاری با کانفیگ قدیمی `peer_ip`
- امکان اجرای Hub بدون Peer اولیه
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

پورت‌های مورد نیاز:

| سرویس | پورت پیش‌فرض | توضیح |
|---|---:|---|
| Panel | `8088/tcp` | پنل گرافیکی VTP |
| EasyTier Tunnel 1 | `2070/tcp` | Listener تونل اول |
| EasyTier Tunnel 2 | `2071/tcp` | Listener تونل دوم، به‌صورت خودکار یکتا می‌شود |
| RPC Tunnel 1 | `15888/tcp` روی localhost | برای کنترل EasyTier |
| RPC Tunnel 2 | `15889/tcp` روی localhost | برای تونل دوم |

## نصب سریع

داخل پوشه پروژه اجرا کنید:

```bash
git clone https://github.com/Unknown-sir/VTP.git
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

Token پنل همیشه در این مسیر ذخیره می‌شود:

```bash
sudo cat /etc/vortexl2/panel_token
```

## ورود به پنل

در مرورگر باز کنید:

```text
http://SERVER_IP:8088
```

سپس Token را وارد کنید.

پنل شامل بخش‌های جداگانه است:

1. وضعیت کلی
2. ساخت تونل مرحله‌ای
3. مدیریت تونل‌ها
4. Port Forwarding
5. عیب‌یابی و لاگ

## ساخت سناریوی یک خارج به چند ایران

### مرحله ۱: نصب روی سرور خارج

روی سرور خارج نصب را اجرا کنید:

```bash
sudo bash install.sh
```

وارد پنل شوید و از بخش **ساخت تونل مرحله‌ای** گزینه **خارج / Hub** را انتخاب کنید.

مقادیر پیشنهادی:

```text
Name: kharej-hub
Role: خارج / Hub
Local IP: 10.155.155.1
Secret: یک مقدار دلخواه، ولی مشترک بین همه سرورها
Peers: خالی
```

برای Hub لازم نیست Peer وارد شود. ایران‌ها می‌توانند به IP عمومی سرور خارج وصل شوند.

### مرحله ۲: نصب روی سرور ایران 1

روی سرور ایران اول نصب را اجرا کنید، وارد پنل شوید و گزینه **ایران / Node** را انتخاب کنید.

مقادیر پیشنهادی:

```text
Name: iran1
Role: ایران / Node
Local IP: 10.155.155.2
Secret: همان Secret سرور خارج
Peers:
KHAREJ_PUBLIC_IP:2070 # kharej
```

### مرحله ۳: نصب روی سرور ایران 2

روی سرور ایران دوم هم همین کار را انجام دهید، فقط IP داخلی را متفاوت بگذارید:

```text
Name: iran2
Role: ایران / Node
Local IP: 10.155.155.3
Secret: همان Secret سرور خارج
Peers:
KHAREJ_PUBLIC_IP:2070 # kharej
```

## نکته مهم درباره چند Tunnel روی یک سرور

در نسخه‌های قبلی، تونل دوم ممکن بود اجرا نشود چون مقدارهایی مثل `tun1`، پورت `2070` و RPC پورت `15888` تکراری می‌شدند.

در این نسخه برای هر Tunnel مقدارهای جدید ساخته می‌شود:

```text
tunnel1:
  interface_name: tun1
  local_ip: 10.155.155.1
  port: 2070
  rpc_port: 15888

tunnel2:
  interface_name: tun2
  local_ip: 10.155.156.1
  port: 2071
  rpc_port: 15889
```

قبل از Start، پروژه conflict را بررسی می‌کند و اگر چیزی تکراری باشد خطای دقیق نشان می‌دهد.

## EasyTier نصب نشد یا داخل پنل نوشته شد not found

اگر داخل پنل در بخش وضعیت کلی نوشته شد:

```text
EasyTier: not found
```

از همان بخش روی دکمه **نصب خودکار EasyTier** کلیک کنید.

همچنین می‌توانید نصب را دوباره اجرا کنید:

```bash
sudo bash install.sh
```

برای بررسی وضعیت:

```bash
sudo vtp-doctor
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

اگر هنوز هیچ پورت Forward تعریف نشده باشد، HAProxy دیگر خطای زیر را نمی‌دهد:

```text
Configuration file has no error but will not start (no listener)
```

در این حالت پنل پیام می‌دهد که HAProxy آماده است، اما چون listener وجود ندارد سرویس اجرا نمی‌شود. بعد از تعریف پورت، HAProxy به‌صورت عادی Start می‌شود.

## مسیر فایل‌ها

```text
/opt/vortexl2                         فایل‌های برنامه
/etc/vortexl2/config.yaml             تنظیمات کلی
/etc/vortexl2/panel_token             توکن ورود پنل
/etc/vortexl2/tunnels/*.yaml          تنظیمات تونل‌ها
/etc/systemd/system/vortexl2-panel.service
/etc/systemd/system/vortexl2-forward-daemon.service
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

لاگ تونل‌ها:

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
- IP داخلی EasyTier تکراری است
- Peer اشتباه وارد شده است
- پورت Listener یا RPC با سرویس دیگری conflict دارد
