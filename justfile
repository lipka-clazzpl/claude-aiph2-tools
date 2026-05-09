default:
    @just --list

# Zainstaluj zaleznosci
install:
    uv sync
    @cp -n .env.sample .env 2>/dev/null && echo "Utworzono .env z .env.sample - uzupelnij ANTHROPIC_API_KEY." || echo ".env juz istnieje - sprawdz czy ANTHROPIC_API_KEY jest ustawiony."

# Interaktywny REPL
run:
    CLAUDECODE= uv run python learn_agent.py

# Boot REPL z auto-uruchomieniem /learn-quest <slug>
run-day SLUG:
    CLAUDECODE= uv run python learn_agent.py --quest {{SLUG}}

# Sesja powtorek (one-shot)
review:
    CLAUDECODE= uv run python learn_agent.py --review

# Karty zaplanowane na dzis (bez agenta, czysty SM-2)
due:
    uv run python -c "import asyncio; from modules.tools import due_today; print(asyncio.run(due_today({}))['content'][0]['text'])"

# Lista wszystkich kart
list:
    uv run python -c "import asyncio; from modules.tools import list_cards; print(asyncio.run(list_cards({}))['content'][0]['text'])"

# Hint do priming kontekstu w Claude Code
prime:
    @echo "Run /prime in Claude Code in this dir"

# Symuluj learn-agenta w nowej sesji Claude Code (Sonnet 4.6 1M + SYSTEM_PROMPT + /prime)
metacc:
    claude --model 'sonnet[1m]' --append-system-prompt "$(cat prompts/SYSTEM_PROMPT.md)" /prime
