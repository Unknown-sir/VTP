try:
    from rich.console import Console
except Exception:
    class Console:
        def print(self, *args, **kwargs): print(*args)
console = Console()

def show_error(msg): console.print(f"[red]{msg}[/]")
def show_success(msg): console.print(f"[green]{msg}[/]")
def show_warning(msg): console.print(f"[yellow]{msg}[/]")
def show_info(msg): console.print(f"[cyan]{msg}[/]")
def show_banner(): console.print("[bold magenta]VortexL2 Panel Edition[/]")
def wait_for_enter(): input("Press Enter to continue...")
def show_output(msg, title="Output"): console.print(f"[bold]{title}[/]\n{msg}")
