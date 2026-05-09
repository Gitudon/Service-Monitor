from common import *
from use_mysql import UseMySQL

intent = discord.Intents.default()
intent.message_content = True
client = commands.Bot(command_prefix="?", intents=intent)
task = None


class ServiceMonitor:
    @staticmethod
    async def sleep_to_next_time():
        now = datetime.datetime.now()
        if 0 <= now.minute < 15:
            next_time = now.replace(minute=15, second=0, microsecond=0)
        elif 15 <= now.minute < 30:
            next_time = now.replace(minute=30, second=0, microsecond=0)
        elif 30 <= now.minute < 45:
            next_time = now.replace(minute=45, second=0, microsecond=0)
        else:
            next_time = (now + datetime.timedelta(hours=1)).replace(
                minute=0, second=0, microsecond=0
            )

        seconds_until = max(
            0, math.ceil((next_time - datetime.datetime.now()).total_seconds())
        )
        await write_log_message(f"Sleeping for {seconds_until} seconds...", "INFO")
        await asyncio.sleep(seconds_until)

    @staticmethod
    async def send_alert_message(message: str):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await client.get_channel(ALERT_CHANNEL_ID).send(f"{timestamp}\n{message}")

    @classmethod
    async def ping_to_servers(cls):
        servers = {}
        with open("./secrets/server_ip_addresses.dat", "r") as f:
            for line in f.read().splitlines():
                if not line.strip():
                    continue
                ip_address, server_name = line.strip().split()
                servers[server_name] = ip_address
        for server_name, ip_address in servers.items():
            try:
                ping_success = False
                for _ in range(5):
                    await asyncio.sleep(1)
                    process = await asyncio.create_subprocess_exec(
                        "ping",
                        "-c",
                        "1",
                        "-W",
                        "3",
                        ip_address,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await process.communicate()
                    if process.returncode == 0:
                        ping_success = True
                        break
                if not ping_success:
                    await cls.send_alert_message(
                        f"{ip_address} {server_name}\nping応答なし(5回連続)"
                    )
            except Exception as e:
                await write_log_message(f"{e}", "ERROR")
                traceback.print_exc()
                await cls.send_alert_message(
                    f"{ip_address} {server_name}\nping応答確認中にエラーが発生"
                )

    @classmethod
    async def check_tcp_port(cls, ip_address: str, port: str, service_name: str):
        try:
            await asyncio.sleep(1)
            ssh_success = False
            for _ in range(5):
                process = await asyncio.create_subprocess_exec(
                    "nc",
                    "-zv",
                    "-w",
                    "5",
                    ip_address,
                    port,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await process.communicate()
                if process.returncode == 0:
                    ssh_success = True
                    break
            if not ssh_success:
                await cls.send_alert_message(
                    f"{ip_address}:{port} {service_name}\nこのポートからの応答なし(5回連続)"
                )
        except Exception as e:
            await write_log_message(f"{e}", "ERROR")
            traceback.print_exc()
            await cls.send_alert_message(
                f"{ip_address}:{port} {service_name}\nTCP接続確認中にエラーが発生"
            )

    @classmethod
    async def check_http_service(cls, ip_address: str, port: str, service_name: str):
        try:
            await asyncio.sleep(1)
            url = (
                f"http://{ip_address}"
                if port == "80"
                else f"http://{ip_address}:{port}"
            )
            process = await asyncio.create_subprocess_exec(
                "curl",
                "-I",
                "-s",
                "-m",
                "5",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode != 0 or b"HTTP/" not in stdout:
                await cls.send_alert_message(
                    f"{ip_address}:{port} {service_name}\nHTTPの応答なし"
                )
        except Exception as e:
            await write_log_message(f"{e}", "ERROR")
            traceback.print_exc()
            await cls.send_alert_message(
                f"{ip_address}:{port} {service_name}\nHTTP応答確認中にエラーが発生"
            )

    @classmethod
    async def check_server_services(cls):
        ip_addresses = {}
        with open("./secrets/services_to_check.dat", "r") as f:
            for line in f.read().splitlines():
                if not line.strip():
                    continue
                ip_address, port = line.strip().split(":")
                if ip_address not in ip_addresses:
                    ip_addresses[ip_address] = []
                ip_addresses[ip_address].append(port)
        for ip_address, ports in ip_addresses.items():
            for port in ports:
                if port == "80":
                    await cls.check_http_service(ip_address, port, "Apache")
                elif port == "19999":
                    await cls.check_http_service(ip_address, port, "Netdata")
                elif port == "22":
                    await cls.check_tcp_port(ip_address, port, "SSH")
                else:
                    await cls.check_tcp_port(ip_address, port, "不明なサービス")

    @classmethod
    async def check_api_endpoints(cls):
        endpoints = {}
        with open("./secrets/apis_to_check.dat", "r") as f:
            for line in f.read().splitlines():
                if not line.strip():
                    continue
                endpoint, api_name = line.strip().split()
                endpoints[endpoint] = api_name
        for endpoint, api_name in endpoints.items():
            try:
                await asyncio.sleep(1)
                process = await asyncio.create_subprocess_exec(
                    "curl",
                    "-s",
                    "-m",
                    "5",
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    endpoint,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await process.communicate()
                status_code_str = stdout.decode("utf-8").strip()
                if process.returncode != 0 or status_code_str == "000":
                    await cls.send_alert_message(
                        f"{endpoint} {api_name}\ncURL接続に失敗 "
                    )
                    continue
                try:
                    status_code = int(status_code_str)
                    if not (200 <= status_code < 300):
                        await cls.send_alert_message(
                            f"{endpoint} {api_name}\ncURL接続時に異常なステータスコード({status_code})を検知"
                        )
                except ValueError:
                    await cls.send_alert_message(
                        f"{endpoint} {api_name}\ncURL接続時に不明なステータスコード({status_code_str})を検知"
                    )
            except Exception as e:
                await write_log_message(f"{e}", "ERROR")
                traceback.print_exc()
                await cls.send_alert_message(
                    f"{endpoint} {api_name}\ncURL接続確認中にエラーが発生"
                )

    @classmethod
    async def check_crawlers(cls):
        crawlers = {}
        with open("./secrets/crawlers_to_check.dat", "r") as f:
            for line in f.read().splitlines():
                if not line.strip():
                    continue
                service, method = line.strip().split()
                if service not in crawlers:
                    crawlers[service] = []
                crawlers[service].append(method)
        for service, methods in crawlers.items():
            for method in methods:
                try:
                    await asyncio.sleep(1)
                    latest_crawl_record = await UseMySQL.run_sql(
                        "SELECT id, created_at FROM crawls WHERE service = %s AND method = %s ORDER BY created_at DESC LIMIT 1",
                        (service, method),
                    )
                    if not latest_crawl_record:
                        return
                    now = datetime.datetime.now()
                    latest_crawl_time = latest_crawl_record[0][1]
                    threshold_seconds = 60 * 10
                    if "API" in method:
                        threshold_seconds = 60 * 30
                        latest_crawl_status = await UseMySQL.run_sql(
                            "SELECT status_code FROM api_status_codes WHERE crawl_id = %s ORDER BY created_at DESC LIMIT 1",
                            (latest_crawl_record[0][0],),
                        )
                        status_code = latest_crawl_status[0][0]
                        if status_code != 200:
                            await cls.send_alert_message(
                                f"{service}({method})\n最新APIクロール時に異常なステータスコード({status_code})を検知"
                            )
                    if (now - latest_crawl_time).total_seconds() >= threshold_seconds:
                        await cls.send_alert_message(
                            f"{service}({method})\n{threshold_seconds // 60}分以上クロール記録なし"
                        )
                except Exception as e:
                    await write_log_message(f"{e}", "ERROR")
                    traceback.print_exc()
                    await cls.send_alert_message(
                        f"{service}({method})\n最新クロール状況確認中にエラーが発生"
                    )


async def main():
    while True:
        try:
            await ServiceMonitor.ping_to_servers()
            await ServiceMonitor.check_server_services()
            await ServiceMonitor.check_api_endpoints()
            await ServiceMonitor.check_crawlers()
        except Exception as e:
            await write_log_message(f"{e}", "ERROR")
            traceback.print_exc()
            await ServiceMonitor.send_alert_message("サービス監視中にエラーが発生")
        await ServiceMonitor.sleep_to_next_time()


@client.command()
async def test(ctx):
    if ctx.channel.id == TEST_CHANNEL_ID:
        await ctx.channel.send("Service Monitor Bot is Working!")


@client.event
async def on_ready():
    global task
    try:
        await UseMySQL.init_pool()
    except Exception as e:
        await write_log_message(f"{e}", "ERROR")
        traceback.print_exc()
        await ServiceMonitor.send_alert_message("MySQL接続中にエラーが発生")
    await write_log_message("Bot is ready!", "INFO")
    if task is None or task.done():
        task = asyncio.create_task(main())


client.run(TOKEN, log_handler=None)
