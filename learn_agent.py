#!/usr/bin/env python3
"""AIPH2 Active Learning Agent — interaktywny REPL z aktywnym uczeniem,
uczeniem inkrementalnym (SM-2) i profilem zainteresowań."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import readline  # noqa: F401  enables arrow-key / ^U line editing in input()
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from modules import learning_tools_server
from modules import sm2
from modules import streaming_display

console = Console()


def _load_prompt(name: str, fallback: str = "") -> str:
    path = Path(__file__).resolve().parent / "prompts" / name
    if not path.exists():
        return fallback
    return path.read_text(encoding="utf-8").strip()


def _learning_dir() -> Path:
    return Path(os.environ.get("AIPH2_LEARNING_DIR") or sm2.LEARNING_DIR)


def display_startup_banner():
    console.clear()
    banner = Panel(
        "[bold cyan]AIPH2 Active Learning Agent[/bold cyan]\n"
        "[dim]Interaktywny REPL z 5 zasadami aktywnego uczenia, IL+SM-2 i profilem zainteresowań[/dim]\n"
        f"[dim cyan]LEARNING_DIR: {_learning_dir()}[/dim cyan]",
        title="[bold]AIPH2[/bold]",
        border_style="cyan",
    )
    console.print(banner)
    console.print()


SLASH_HELP_ROWS: list[tuple[str, str]] = [
    ("<dowolny tekst>", "Kontynuuj rozmowe / odpowiedz"),
    ("/learn <temat>", "Rozpocznij sesje nauki na dany temat"),
    ("/learn-file <sciezka>", "Zaladuj plik i ucz sie z niego"),
    ("/learn-web <url>", "Pobierz tresc z URL i ucz sie"),
    ("/learn-quest <slug>", "Przeprowadz quest dnia (np. w1d2-2026-04-22-fundamenty)"),
    ("/due", "Pokaz karty zaplanowane na dzis"),
    ("/review", "Sesja powtorek (przod -> tworz odpowiedz -> tyl -> ocena 0-5)"),
    ("/cards [filtr]", "Lista wszystkich kart (opcjonalny filtr po quest/tag/typie)"),
    ("/interest [topic priority]", "Czytaj profil zainteresowań / ustaw priorytet manualnie"),
    ("/wiki <haslo>", "Pociagnij galaz wiedzy z Wikipedii (PL z fallbackiem EN)"),
    ("/save-anki [nazwa]", "Eksport kart do CSV gotowego dla Anki"),
    ("/stats", "Statystyki sesji"),
    ("/clear", "Wyczysc historie rozmowy"),
    ("/help", "Pokaz te pomoc"),
    ("/exit", "Wyjdz"),
]


def _build_command_palette() -> str:
    """One-line dim listing of slash commands. Param placeholders are dimmer."""
    parts: list[str] = []
    for cmd, _desc in SLASH_HELP_ROWS:
        if cmd.startswith("<"):
            continue  # the "any text" entry — not a slash command
        if " " in cmd:
            head, tail = cmd.split(" ", 1)
            parts.append(f"[cyan]{head}[/cyan] [grey50]{tail}[/grey50]")
        else:
            parts.append(f"[cyan]{cmd}[/cyan]")
    return "[dim]" + "  ".join(parts) + "[/dim]"


def display_help():
    table = Table(title="Dostepne komendy", title_style="bold cyan")
    table.add_column("Komenda", style="yellow", no_wrap=True)
    table.add_column("Opis", style="white")
    for cmd, desc in SLASH_HELP_ROWS:
        table.add_row(cmd, desc)
    console.print(table)
    console.print()


def display_tool_use(block: ToolUseBlock):
    console.print(Panel(block.name, title="Wywolane narzedzie", border_style="cyan", style="dim"))


def display_tool_result(block: ToolResultBlock, tool_name: Optional[str] = None):
    status = "+" if not block.is_error else "x"
    color = "green" if not block.is_error else "red"
    if block.content is None:
        content = "No output"
    elif isinstance(block.content, str):
        content = block.content
    elif isinstance(block.content, list):
        content = json.dumps(block.content, indent=2, ensure_ascii=False)
    else:
        content = str(block.content)
    if len(content) > 1500:
        content = content[:1497] + "..."
    title = f"{status} Wynik {tool_name}" if tool_name else f"{status} Wynik narzedzia"
    console.print(Panel(content, title=title, border_style=color, expand=False))


def display_thinking(block: ThinkingBlock):
    console.print(
        Panel(
            Text(block.thinking, style="italic purple"),
            title="[yellow]Mysli agenta[/yellow]",
            border_style="dim",
            expand=False,
        )
    )


def display_session_stats(repl: "LearningAgentREPL"):
    table = Table(title="Statystyki sesji", title_style="bold blue")
    table.add_column("Metryka", style="cyan", no_wrap=True)
    table.add_column("Wartosc", style="yellow")
    duration = (datetime.now() - repl.session_started).total_seconds()
    table.add_row("Czas sesji", f"{int(duration)}s")
    table.add_row("Zapytania", str(repl.queries))
    table.add_row("Odpowiedzi w historii", str(len(repl.history)))
    table.add_row("Karty dodane", str(repl.cards_added))
    table.add_row("Karty powtorzone", str(repl.cards_reviewed))
    if repl.session_id:
        table.add_row("ID sesji", repl.session_id)
    if repl.last_cost is not None:
        table.add_row("Ostatni koszt", f"${repl.last_cost:.6f}")
    console.print(table)
    console.print()


class LearningAgentREPL:
    def __init__(self):
        self.client: Optional[ClaudeSDKClient] = None
        self.session_id: Optional[str] = None
        self.session_started = datetime.now()

        self.queries = 0
        self.cards_added = 0
        self.cards_reviewed = 0
        self.last_cost: Optional[float] = None

        self.history: list[str] = []
        self.last_response: str = ""

        self.system_prompt = _load_prompt(
            "SYSTEM_PROMPT.md",
            fallback=(
                "Jestes agentem aktywnego uczenia AIPH2. Rozmawiaj po polsku. "
                "Stosuj 5 zasad aktywnego uczenia. Po kazdym koncepcie zapisuj "
                "kompletna karte przez add_card_full (z dosolwnym cytatem ze zrodla)."
            ),
        )
        self.learn_quest_template = _load_prompt("LEARN_QUEST.md")
        self.learn_file_template = _load_prompt("LEARN_FILE.md")
        self.review_template = _load_prompt("REVIEW_SESSION.md")

        self.allowed_tools = [
            "mcp__learning__add_card_full",
            "mcp__learning__save_dialog_round",
            "mcp__learning__record_interest",
            "mcp__learning__read_interest_profile",
            "mcp__learning__load_quest_materials",
            "mcp__learning__due_today",
            "mcp__learning__record_review",
            "mcp__learning__list_cards",
            "mcp__learning__export_anki",
            "mcp__learning__load_learning_material",
            "mcp__learning__wikipedia_lookup",
            "Read",
            "WebFetch",
            "WebSearch",
            "Bash",
            "Glob",
            "Grep",
        ]
        self.disallowed_tools = [
            "Write",
            "Edit",
            "MultiEdit",
            "NotebookEdit",
            "Task",
            "TodoWrite",
            "ExitPlanMode",
            "BashOutput",
            "KillShell",
        ]

    async def initialize_client(self):
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:
                pass

        options = ClaudeAgentOptions(
            system_prompt=self.system_prompt,
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
            model="claude-sonnet-4-6",
            mcp_servers={"learning": learning_tools_server},
        )
        self.client = ClaudeSDKClient(options)
        await self.client.connect()
        console.print("[green]+ Klient zainicjalizowany[/green]\n")

    async def _translate_messages(self):
        """Translate SDK messages into streaming_display events.

        Yields ("text", chunk) | ("tool_call", name) | ("tool_result", content)
        | ("thinking", text). Updates tool_use_map, cards_added / cards_reviewed,
        session_id and last_cost as a side-effect. Note: consecutive text blocks
        are joined with "\n\n" by appending the separator to each yielded chunk
        (except the last) to preserve the original join semantics.
        """
        tool_use_map: dict[str, str] = {}

        async for message in self.client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        if block.text and block.text.strip():
                            yield ("text", block.text + "\n\n")
                    elif isinstance(block, ToolUseBlock):
                        tool_use_map[block.id] = block.name
                        if block.name.endswith("add_card_full"):
                            self.cards_added += 1
                        elif block.name.endswith("record_review"):
                            self.cards_reviewed += 1
                        yield ("tool_call", block.name)
                    elif isinstance(block, ToolResultBlock):
                        if block.content is None:
                            content = "No output"
                        elif isinstance(block.content, str):
                            content = block.content
                        elif isinstance(block.content, list):
                            content = json.dumps(
                                block.content, indent=2, ensure_ascii=False
                            )
                        else:
                            content = str(block.content)
                        yield ("tool_result", content[:200])
                    elif isinstance(block, ThinkingBlock):
                        yield ("thinking", block.thinking[:200])
            elif isinstance(message, SystemMessage):
                # Skip noisy system messages by default
                pass
            elif isinstance(message, ResultMessage):
                self.session_id = getattr(message, "session_id", None)
                self.last_cost = getattr(message, "total_cost_usd", None)

    async def process_query(self, query: str, display: str | None = None):
        if self.client is None:
            console.print("[red]Klient nie jest zainicjalizowany[/red]")
            return

        self.queries += 1
        text_to_show = display or query
        console.print(f"\n[bold yellow]› {text_to_show}[/bold yellow]")

        with console.status("[cyan]Laczenie...[/cyan]", spinner="dots"):
            await self.client.query(query)

        full_response = await streaming_display.stream_into_panel(
            self._translate_messages(),
            title="Agent",
        )

        if not full_response.strip():
            return

        self.last_response = full_response
        self.history.append(full_response)


# ---- Slash command handlers ------------------------------------------------


async def _cmd_learn(repl: LearningAgentREPL, args: str) -> bool:
    if not args:
        console.print("[yellow]Uzycie: /learn <temat>[/yellow]")
        return True
    prompt = (
        f"Rozpocznij interaktywna sesje nauki na temat: {args}.\n"
        "Stosuj 5 zasad aktywnego uczenia. Po kazdym konkretnym koncepcie "
        "zapisz kompletna karte przez add_card_full (z dosolwnym cytatem zrodla "
        "i runda dialogu)."
    )
    await repl.process_query(prompt, display=f"/learn {args}")
    return True


async def _cmd_learn_file(repl: LearningAgentREPL, args: str) -> bool:
    if not args:
        console.print("[yellow]Uzycie: /learn-file <sciezka>[/yellow]")
        return True
    resolved = Path(args)
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    if repl.learn_file_template:
        prompt = repl.learn_file_template.replace("{file_path}", str(resolved))
    else:
        prompt = (
            f"Zaladuj plik {resolved} przez load_learning_material lub Read i "
            "naucz mnie jego zawartosci krok po kroku. Po kazdym koncepcie zapisz "
            "karte przez add_card_full."
        )
    await repl.process_query(prompt, display=f"/learn-file {args}")
    return True


async def _cmd_learn_web(repl: LearningAgentREPL, args: str) -> bool:
    if not args:
        console.print("[yellow]Uzycie: /learn-web <url>[/yellow]")
        return True
    prompt = (
        f"Pobierz tresc ze strony {args} przez WebFetch, przeanalizuj material i "
        "rozpocznij interaktywna sesje nauki. Po kazdym koncepcie zapisz karte "
        "przez add_card_full."
    )
    await repl.process_query(prompt, display=f"/learn-web {args}")
    return True


async def _cmd_learn_quest(repl: LearningAgentREPL, args: str) -> bool:
    if not args:
        console.print(
            "[yellow]Uzycie: /learn-quest <slug>  np. w1d2-2026-04-22-fundamenty[/yellow]"
        )
        return True
    if repl.learn_quest_template:
        prompt = repl.learn_quest_template.replace("{slug}", args)
    else:
        prompt = (
            f"Zaladuj materialy questa {args} przez load_quest_materials. "
            "Wczytaj tez profil zainteresowań przez read_interest_profile. "
            "Zaproponuj plan sesji (lista konceptow), poczekaj na potwierdzenie, "
            "potem przeprowadz mnie krok po kroku zgodnie z 5 zasadami aktywnego "
            "uczenia. Po kazdym koncepcie zapisz pelna karte przez add_card_full."
        )
    await repl.process_query(prompt, display=f"/learn-quest {args}")
    return True


async def _cmd_due(repl: LearningAgentREPL, args: str) -> bool:
    prompt = (
        "Wywolaj due_today i pokaz mi karty zaplanowane na dzis. "
        "Posortowane po priorytecie (najnizszy numer pierwszy). "
        "Zapytaj czy chce rozpoczac powtorki przez /review."
    )
    await repl.process_query(prompt, display="/due")
    return True


async def _cmd_review(repl: LearningAgentREPL, args: str) -> bool:
    if repl.review_template:
        prompt = repl.review_template
    else:
        prompt = (
            "Wywolaj due_today aby zobaczyc karty do powtorki. Dla kazdej karty: "
            "pokaz tylko Kontekst, Cytat zrodlowy i Pytanie sprawdzajace (przod). "
            "Poczekaj az sprobuje odpowiedziec. Dopiero wtedy pokaz Sedno, Korekte "
            "i Element review (tyl). Zapytaj o ocene 0-5 i wywolaj record_review."
        )
    await repl.process_query(prompt, display="/review")
    return True


async def _cmd_cards(repl: LearningAgentREPL, args: str) -> bool:
    extra = f" Filtr: {args}." if args else ""
    prompt = f"Wywolaj list_cards.{extra} Pokaz wynik w czytelnej formie."
    await repl.process_query(prompt, display=f"/cards {args}".rstrip())
    return True


async def _cmd_interest(repl: LearningAgentREPL, args: str) -> bool:
    parts = args.split()
    if len(parts) >= 2:
        topic = parts[0]
        try:
            priority = int(parts[1])
        except ValueError:
            console.print("[yellow]Uzycie: /interest <topic> <0-100>[/yellow]")
            return True
        prompt = (
            f"Wywolaj record_interest z topic='{topic}', signal='manual /interest', "
            f"i ustaw priorytet na {priority} (mozesz uzyc set_priority bezposrednio "
            "albo wyliczyc weight_delta). Pokaz aktualny stan profilu."
        )
    else:
        prompt = "Wywolaj read_interest_profile i pokaz mi profil zainteresowań."
    await repl.process_query(prompt, display=f"/interest {args}".rstrip())
    return True


async def _cmd_save_anki(repl: LearningAgentREPL, args: str) -> bool:
    name = args.strip() or f"aiph2-anki-{datetime.now():%Y%m%d-%H%M}"
    prompt = (
        f"Wywolaj export_anki z filename='{name}' i scope='all'. "
        "Pokaz sciezke pliku i liczbe wyeksportowanych kart."
    )
    await repl.process_query(prompt, display=f"/save-anki {name}")
    return True


async def _cmd_stats(repl: LearningAgentREPL, args: str) -> bool:
    display_session_stats(repl)
    return True


async def _cmd_clear(repl: LearningAgentREPL, args: str) -> bool:
    repl.history.clear()
    repl.last_response = ""
    repl.queries = 0
    repl.cards_added = 0
    repl.cards_reviewed = 0
    repl.session_id = None
    await repl.initialize_client()
    console.print("[green]+ Historia i klient wyczyszczone[/green]\n")
    return True


async def _cmd_help(repl: LearningAgentREPL, args: str) -> bool:
    display_help()
    return True


async def _cmd_exit(repl: LearningAgentREPL, args: str) -> bool:
    console.print("\n[yellow]Do zobaczenia![/yellow]")
    return False


async def _cmd_wiki(repl: LearningAgentREPL, args: str) -> bool:
    if not args:
        console.print("[yellow]Uzycie: /wiki <haslo>  np. /wiki Lean Startup[/yellow]")
        return True
    prompt = (
        f"Wywołaj wikipedia_lookup z title='{args}', lang='auto', branches=3, mode='full'. "
        "Pokaż streszczenie i 3 powiązane gałęzie z URLami. "
        "NIE zapisuj karty — to manualny lookup, nie pętla nauczania."
    )
    await repl.process_query(prompt, display=f"/wiki {args}")
    return True


SLASH_COMMANDS = {
    "/learn": _cmd_learn,
    "/learn-file": _cmd_learn_file,
    "/learn-web": _cmd_learn_web,
    "/learn-quest": _cmd_learn_quest,
    "/due": _cmd_due,
    "/review": _cmd_review,
    "/cards": _cmd_cards,
    "/interest": _cmd_interest,
    "/wiki": _cmd_wiki,
    "/save-anki": _cmd_save_anki,
    "/stats": _cmd_stats,
    "/clear": _cmd_clear,
    "/help": _cmd_help,
    "/exit": _cmd_exit,
    "/quit": _cmd_exit,
}


# ---- Main loop -------------------------------------------------------------


async def _run_repl(initial_command: Optional[str] = None) -> int:
    repl = LearningAgentREPL()
    display_startup_banner()
    await repl.initialize_client()
    console.print("[dim]Wpisz '/help' by zobaczyc komendy, '/exit' by wyjsc.[/dim]\n")

    if initial_command:
        cmd_token = initial_command.split(maxsplit=1)[0]
        rest = initial_command[len(cmd_token):].strip()
        handler = SLASH_COMMANDS.get(cmd_token)
        if handler is not None:
            try:
                await handler(repl, rest)
            except Exception as e:
                console.print(Panel(f"[red]{e}[/red]", title="[red]Blad[/red]"))

    # Persistent command palette + colored AIPH2[N] header are printed on
    # their own lines before each prompt. The actual input() call uses a
    # plain "› " prompt — readline manages a clean line, libedit on macOS
    # can't be relied on to honour the \x01…\x02 width markers, so colored
    # text inside input()'s prompt would either get stripped or misalign
    # cursor maths. Putting the colored part above the input line side-
    # steps both problems.
    palette_line = _build_command_palette()

    def _render_prompt_header(n: int) -> None:
        console.print(palette_line, highlight=False)
        console.print(f"[bold cyan]AIPH2[{n}][/bold cyan]", highlight=False)

    try:
        while True:
            try:
                _render_prompt_header(repl.queries)
                user_input = input("› ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                cmd_token = user_input.split(maxsplit=1)[0]
                rest = user_input[len(cmd_token):].strip()
                handler = SLASH_COMMANDS.get(cmd_token)
                if handler is not None:
                    try:
                        cont = await handler(repl, rest)
                    except Exception as e:
                        console.print(Panel(f"[red]{e}[/red]", title="[red]Blad[/red]"))
                        cont = True
                    if not cont:
                        break
                    continue
                # Unknown slash — fall through to model

            try:
                await repl.process_query(user_input)
            except Exception as e:
                console.print(Panel(f"[red]{e}[/red]", title="[red]Blad[/red]"))

    finally:
        if repl.client is not None:
            try:
                await repl.client.disconnect()
            except Exception:
                pass

    return 0


def _parse_args(argv: list[str]) -> tuple[Optional[str], argparse.Namespace]:
    parser = argparse.ArgumentParser(prog="learn_agent")
    parser.add_argument("--quest", metavar="SLUG", help="Uruchom automatycznie /learn-quest <slug>")
    parser.add_argument("--review", action="store_true", help="Uruchom automatycznie /review")
    parser.add_argument("--learn", metavar="TOPIC", help="Uruchom automatycznie /learn <topic>")
    args = parser.parse_args(argv)
    initial = None
    if args.quest:
        initial = f"/learn-quest {args.quest}"
    elif args.review:
        initial = "/review"
    elif args.learn:
        initial = f"/learn {args.learn}"
    return initial, args


def main() -> int:
    initial, _ = _parse_args(sys.argv[1:])
    try:
        return asyncio.run(_run_repl(initial))
    except KeyboardInterrupt:
        console.print("\n[yellow]Przerwano[/yellow]")
        return 0


if __name__ == "__main__":
    sys.exit(main())
