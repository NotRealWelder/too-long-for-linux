#!/usr/bin/env python3
"""
Проверка и исправление длинных путей/имен файлов в Linux.
v0.5 (25.11.25)
"""

import argparse
import logging
import os
import shutil
import sys
from collections.abc import Generator
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path


# --- Константы ---
MAX_FILENAME_BYTES = 255
MAX_PATH_BYTES = 4096
SAFE_LENGTH = 250
SAFE_STEM_LENGTH = 200


class Colors:
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    RESET = "\033[0m"


class ProblemType(Enum):
    FILE_NAME = auto()
    DIR_NAME = auto()
    FILE_PATH = auto()
    DIR_PATH = auto()


@dataclass
class Problem:
    type: ProblemType
    current_length: int
    path: Path

    @property
    def description(self) -> str:
        if self.type in (ProblemType.FILE_NAME, ProblemType.DIR_NAME):
            return f"ДЛИННОЕ ИМЯ [{self.current_length}/{MAX_FILENAME_BYTES}]"
        return f"ДЛИННЫЙ ПУТЬ [{self.current_length}/{MAX_PATH_BYTES}]"


# --- Работа со строками и байтами ---


def count_bytes(s: str) -> int:
    return len(s.encode("utf-8"))


def safe_truncate(s: str, max_bytes: int = SAFE_LENGTH) -> str:
    """Обрезает строку до указанного кол-ва байт, сохраняя валидность UTF-8."""
    if count_bytes(s) <= max_bytes:
        return s
    encoded = s.encode("utf-8")
    # Обрезаем и декодируем с игнорированием ошибок, чтобы убрать битый последний символ
    return encoded[:max_bytes].decode("utf-8", "ignore")


def split_string_utf8(s: str) -> tuple[str, str]:
    """Разделяет строку пополам с учетом границ UTF-8 символов."""
    encoded = s.encode("utf-8")
    split_point = len(encoded) // 2

    # Сдвигаемся назад, пока не найдем начало символа (старшие биты не 10xxxxxx)
    while split_point > 0 and (encoded[split_point] & 0xC0 == 0x80):
        split_point -= 1

    if split_point == 0:
        split_point = len(encoded) // 2  # Fallback

    part1 = encoded[:split_point].decode("utf-8", "ignore")
    part2 = encoded[split_point:].decode("utf-8", "ignore")
    return part1, part2


def get_unique_path(
    directory: Path, stem: str, suffix: str = "", is_dir: bool = False
) -> Path:
    """Генерирует уникальный путь, добавляя счетчик, если файл существует."""
    # Первичная проверка длины
    name = safe_truncate(stem + suffix, SAFE_LENGTH)
    candidate = directory / name

    counter = 1
    while candidate.exists():
        # Формируем имя с счетчиком, обрезая stem, чтобы влезть в лимит
        base_stem = safe_truncate(stem, SAFE_STEM_LENGTH)
        name = f"{base_stem}_{counter}{suffix}"

        # Финальная проверка на случай если суффикс очень длинный
        if count_bytes(name) > MAX_FILENAME_BYTES:
            name = safe_truncate(name, SAFE_LENGTH)

        candidate = directory / name
        counter += 1

    return candidate


# --- Основная логика ---


class Scanner:
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)
        self.total_scanned = 0

    def scan(self, show_progress: bool = True) -> Generator[Problem, None, None]:
        total_items = 0
        if show_progress:
            print("Подсчет файлов...", end=" ", flush=True)
            for _, dirs, files in os.walk(self.root_dir):
                total_items += len(dirs) + len(files)
            print(f"найдено: {total_items}")

        self.total_scanned = 0

        for root, dirs, files in os.walk(self.root_dir):
            # Проверяем директории
            for d in dirs:
                yield from self._check_item(Path(root), d, is_dir=True)
                self._update_progress(show_progress, total_items)

            # Проверяем файлы
            for f in files:
                yield from self._check_item(Path(root), f, is_dir=False)
                self._update_progress(show_progress, total_items)

        if show_progress:
            print(f"\rСканирование: 100.0% ({self.total_scanned}/{self.total_scanned})")

    def _check_item(
        self, root: Path, name: str, is_dir: bool
    ) -> Generator[Problem, None, None]:
        self.total_scanned += 1
        full_path = root / name
        name_len = count_bytes(name)
        path_len = count_bytes(str(full_path))

        if name_len >= MAX_FILENAME_BYTES:
            p_type = ProblemType.DIR_NAME if is_dir else ProblemType.FILE_NAME
            yield Problem(p_type, name_len, full_path)

        if path_len >= MAX_PATH_BYTES:
            p_type = ProblemType.DIR_PATH if is_dir else ProblemType.FILE_PATH
            yield Problem(p_type, path_len, full_path)

    def _update_progress(self, show_progress: bool, total: int):
        if show_progress and total > 0 and self.total_scanned % 100 == 0:
            percent = (self.total_scanned / total) * 100
            print(
                f"\rСканирование: {percent:.1f}% ({self.total_scanned}/{total})",
                end="",
                flush=True,
            )


class Fixer:
    @staticmethod
    def fix_problem(problem: Problem) -> str:
        path_error_msg = "Автоматическое исправление путей пока не поддерживается."
        if "PATH" in problem.type.name:
            raise ValueError(path_error_msg)

        path = problem.path
        parent = path.parent
        original_name = path.name

        # Стратегия разделения (Split)
        if count_bytes(original_name) > MAX_FILENAME_BYTES:
            # Пытаемся разбить имя на папку и файл, чтобы сохранить структуру
            stem = path.stem
            suffix = path.suffix if not path.is_dir() else ""

            # Если имя без расширения тоже гигантское, режем его
            stem_bytes = count_bytes(stem)

            if stem_bytes > 1:
                part1, part2 = split_string_utf8(stem)
                part2 += suffix

                # Обрезаем части если они всё еще велики
                part1 = safe_truncate(part1, SAFE_LENGTH)
                part2 = safe_truncate(part2, SAFE_LENGTH)

                # Создаем папку из первой части
                new_parent_dir = get_unique_path(parent, part1, is_dir=True)
                new_parent_dir.mkdir(parents=True, exist_ok=True)

                # Перемещаем внутрь новой папки
                new_path = get_unique_path(
                    new_parent_dir, Path(part2).stem, Path(part2).suffix
                )

                shutil.move(str(path), str(new_path))

                # Если это была директория, удаляем пустую старую (если shutil.move ее не удалил)
                if path.is_dir() and path.exists() and not any(path.iterdir()):
                    path.rmdir()

                return f"Перемещено (split): {path.name} -> {new_parent_dir.name}/{new_path.name}"

        # Fallback: простое переименование (Truncate)
        safe_name = safe_truncate(original_name, SAFE_LENGTH)
        new_path = get_unique_path(parent, Path(safe_name).stem, Path(safe_name).suffix)

        shutil.move(str(path), str(new_path))
        return f"Переименовано (truncate): {path.name} -> {new_path.name}"


class Reporter:
    @staticmethod
    def print_summary(
        problems: list[Problem],
        total_scanned: int,
        log_file: str | None = None,
        quiet: bool = False,
    ):
        name_problems = [p for p in problems if "NAME" in p.type.name]
        path_problems = [p for p in problems if "PATH" in p.type.name]

        if quiet:
            print(f"{len(name_problems)} {len(path_problems)} {total_scanned}")
            return

        print(f"\n{Colors.BOLD}РЕЗУЛЬТАТЫ ПРОВЕРКИ:{Colors.RESET}")
        print(f"Всего проверено: {Colors.BLUE}{total_scanned}{Colors.RESET}")
        print(
            f"Длинных имен (>255 байт): {Colors.YELLOW}{len(name_problems)}{Colors.RESET}"
        )
        print(
            f"Длинных путей (>4096 байт): {Colors.YELLOW}{len(path_problems)}{Colors.RESET}"
        )

        if not problems:
            print(
                f"\n{Colors.GREEN}Все пути и имена соответствуют ограничениям Linux{Colors.RESET}"
            )
        else:
            print(f"\n{Colors.BOLD}ДЕТАЛИЗАЦИЯ:{Colors.RESET}")
            for p in problems:
                print(f"  {p.description}: {p.path}")

        if log_file:
            Reporter._write_log(log_file, problems)
            print(f"\n{Colors.BLUE}Отчет сохранен в: {log_file}{Colors.RESET}")

    @staticmethod
    def _write_log(filepath: str, problems: list[Problem]):
        try:
            with Path(filepath).open("a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 60}\n")
                f.write(
                    f"Проверка {logging.Formatter('%(asctime)s').format(logging.LogRecord('', 0, '', '', 0, 0, 0))}\n"
                )
                f.write(f"{'=' * 60}\n")
                if not problems:
                    f.write("Нет проблем.\n")
                for p in problems:
                    f.write(f"{p.description}: {p.path}\n")
        except OSError as e:
            print(f"{Colors.RED}Ошибка записи лога: {e}{Colors.RESET}", file=sys.stderr)


# --- Аргументы командной строки ---


def parse_args():
    parser = argparse.ArgumentParser(
        description="Проверка и исправление длинных путей/имен файлов Linux",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "directory", nargs="?", default=".", help="Директория для проверки"
    )
    parser.add_argument(
        "-p", "--no-progress", action="store_true", help="Скрыть прогресс"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Тихий режим")
    parser.add_argument(
        "-l", "--log", nargs="?", const="AUTO", metavar="FILE", help="Файл лога"
    )
    parser.add_argument(
        "--axe", action="store_true", help="АВТОМАТИЧЕСКОЕ исправление имен (опасно!)"
    )
    return parser.parse_args()


# --- Точка входа ---


def main():
    args = parse_args()

    if not Path(args.directory).is_dir():
        print(
            f"{Colors.RED}Ошибка: {args.directory} не является директорией{Colors.RESET}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 1. Сканирование
    scanner = Scanner(args.directory)
    try:
        problems = list(
            scanner.scan(show_progress=not args.no_progress and not args.quiet)
        )
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
        sys.exit(1)

    # 2. Исправление (если запрошено)
    if args.axe and problems:
        print(f"\n{Colors.BOLD}Запуск исправлений...{Colors.RESET}")
        fixed_count = 0
        remaining_problems = []

        for p in problems:
            if "NAME" in p.type.name:
                try:
                    msg = Fixer.fix_problem(p)
                    print(f"  {Colors.GREEN}FIXED:{Colors.RESET} {msg}")
                    fixed_count += 1
                except (OSError, ValueError) as e:
                    print(f"  {Colors.RED}ERROR:{Colors.RESET} {p.path} -> {e}")
                    remaining_problems.append(p)
            else:
                remaining_problems.append(p)  # Пути не чиним

        print(
            f"Исправлено: {fixed_count}/{len(problems) - len([x for x in problems if 'PATH' in x.type.name])}"
        )
        problems = remaining_problems

    # 3. Отчет
    log_name = args.log
    if log_name == "AUTO":
        log_name = f"{Path.cwd().name or 'root'}.LOG"

    Reporter.print_summary(problems, scanner.total_scanned, log_name, args.quiet)

    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
