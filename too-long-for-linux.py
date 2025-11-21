#!/usr/bin/env python3
"""
Проверка длинных путей и имен файлов для Linux с учетом системных ограничений
Используйте ./too-long-for-linux.py --help для вывода справки
v0.4 от 20.11.25
"""

import argparse
import contextlib
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


class Colors:
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def count_bytes(string):
    return len(string.encode("utf-8"))


def safe_truncate(string, max_length=250):
    if count_bytes(string) <= max_length:
        return string
    return string.encode("utf-8")[:max_length].decode("utf-8", "ignore")


def split_filename(filename, max_length=255):
    if count_bytes(filename) <= max_length:
        return filename, None

    stem = Path(filename).stem
    suffix = Path(filename).suffix

    stem_bytes = count_bytes(stem)
    if stem_bytes > 1:
        stem_encoded = stem.encode("utf-8")
        split_point = len(stem_encoded) // 2

        while split_point > 0 and (stem_encoded[split_point] & 0xC0 == 0x80):
            split_point -= 1

        if split_point == 0:
            split_point = len(stem_encoded) // 2  # fallback

        part1 = stem_encoded[:split_point].decode("utf-8", "ignore")
        part2 = stem_encoded[split_point:].decode("utf-8", "ignore") + suffix

        if count_bytes(part1) > 255:
            part1 = safe_truncate(part1, 250)
        if count_bytes(part2) > 255:
            part2 = safe_truncate(part2, 250)

        return part1, part2
    return safe_truncate(filename, 250), None


def split_directory_name(dirname, max_length=255):
    if count_bytes(dirname) <= max_length:
        return dirname, None

    dirname_bytes = count_bytes(dirname)
    if dirname_bytes > 1:
        dirname_encoded = dirname.encode("utf-8")
        split_point = len(dirname_encoded) // 2

        while split_point > 0 and (dirname_encoded[split_point] & 0xC0 == 0x80):
            split_point -= 1

        if split_point == 0:
            split_point = len(dirname_encoded) // 2  # fallback

        part1 = dirname_encoded[:split_point].decode("utf-8", "ignore")
        part2 = dirname_encoded[split_point:].decode("utf-8", "ignore")

        if count_bytes(part1) > 255:
            part1 = safe_truncate(part1, 250)
        if count_bytes(part2) > 255:
            part2 = safe_truncate(part2, 250)

        return part1, part2
    return safe_truncate(dirname, 250), None


def create_safe_directory(base_path, desired_name, max_length=255):
    safe_name = desired_name
    if count_bytes(safe_name) > max_length:
        safe_name = safe_truncate(safe_name, 250)

    full_path = base_path / safe_name

    counter = 1
    while full_path.exists():
        safe_name = f"{Path(desired_name).stem[:200]}_{counter}"
        if count_bytes(safe_name) > max_length:
            safe_name = safe_truncate(safe_name, 250)
        full_path = base_path / safe_name
        counter += 1

    full_path.mkdir(parents=True, exist_ok=True)
    return full_path


def _fix_file_simple(path, parent_dir, original_name):
    new_filename = safe_truncate(original_name, 250)
    new_file_path = parent_dir / new_filename

    counter = 1
    while new_file_path.exists():
        stem = Path(original_name).stem
        suffix = Path(original_name).suffix
        new_filename = f"{stem[:200]}_{counter}{suffix}"
        if count_bytes(new_filename) > 255:
            new_filename = safe_truncate(new_filename, 250)
        new_file_path = parent_dir / new_filename
        counter += 1

    shutil.move(str(path), str(new_file_path))
    return f"Файл переименован: {path} -> {new_file_path}"


def _fix_file_split(path, parent_dir, original_name, part1, part2):
    new_dir = create_safe_directory(parent_dir, part1)

    new_file_path = new_dir / part2

    counter = 1
    while new_file_path.exists():
        stem = Path(part2).stem
        suffix = Path(part2).suffix
        new_part2 = f"{stem[:200]}_{counter}{suffix}"
        if count_bytes(new_part2) > 255:
            new_part2 = safe_truncate(new_part2, 250)
        new_file_path = new_dir / new_part2
        counter += 1

    shutil.move(str(path), str(new_file_path))
    return f"Файл перемещен: {path} -> {new_file_path}"


def _fix_directory_simple(path, parent_dir, original_name):
    new_dir_name = safe_truncate(original_name, 250)
    new_dir_path = parent_dir / new_dir_name

    counter = 1
    while new_dir_path.exists():
        new_dir_name = f"{Path(original_name).stem[:200]}_{counter}"
        if count_bytes(new_dir_name) > 255:
            new_dir_name = safe_truncate(new_dir_name, 250)
        new_dir_path = parent_dir / new_dir_name
        counter += 1

    new_dir_path.mkdir(parents=True, exist_ok=True)

    for item in path.iterdir():
        shutil.move(str(item), str(new_dir_path / item.name))

    with contextlib.suppress(OSError):
        path.rmdir()

    return f"Директория переименована: {path} -> {new_dir_path}"


def _fix_directory_split(path, parent_dir, original_name, part1, part2):
    new_parent_dir = create_safe_directory(parent_dir, part1)

    new_dir_path = new_parent_dir / part2

    counter = 1
    while new_dir_path.exists():
        new_part2 = f"{Path(part2).stem[:200]}_{counter}"
        if count_bytes(new_part2) > 255:
            new_part2 = safe_truncate(new_part2, 250)
        new_dir_path = new_parent_dir / new_part2
        counter += 1

    new_dir_path.mkdir(parents=True, exist_ok=True)

    for item in path.iterdir():
        shutil.move(str(item), str(new_dir_path / item.name))

    with contextlib.suppress(OSError):
        path.rmdir()

    return f"Директория перемещена: {path} -> {new_dir_path}"


def fix_long_name(problem_type, length, path_str):
    path = Path(path_str)

    if "FILE_NAME" in problem_type:
        parent_dir = path.parent
        original_name = path.name

        part1, part2 = split_filename(original_name)

        if part2 is None:
            return _fix_file_simple(path, parent_dir, original_name)
        return _fix_file_split(path, parent_dir, original_name, part1, part2)

    if "DIR_NAME" in problem_type:
        parent_dir = path.parent
        original_name = path.name

        part1, part2 = split_directory_name(original_name)

        if part2 is None:
            return _fix_directory_simple(path, parent_dir, original_name)
        return _fix_directory_split(path, parent_dir, original_name, part1, part2)

    return "Неизвестный тип проблемы"


def scan_directory(directory, show_progress=True):
    problems = []
    total_count = 0

    if show_progress:
        print("Подсчет файлов...", end=" ", flush=True)
        for _root, dirs, files in os.walk(directory):
            total_count += len(dirs) + len(files)
        print(f"найдено: {total_count}")

    current_count = 0

    for root, dirs, files in os.walk(directory):
        for dir_name in dirs:
            current_count += 1
            full_path = Path(root) / dir_name

            name_bytes = count_bytes(dir_name)
            if name_bytes >= 255:
                problems.append(("DIR_NAME", name_bytes, str(full_path)))

            path_bytes = count_bytes(str(full_path))
            if path_bytes >= 4096:
                problems.append(("DIR_PATH", path_bytes, str(full_path)))

            _update_progress(show_progress, current_count, total_count)

        for file_name in files:
            current_count += 1
            full_path = Path(root) / file_name

            name_bytes = count_bytes(file_name)
            if name_bytes >= 255:
                problems.append(("FILE_NAME", name_bytes, str(full_path)))

            path_bytes = count_bytes(str(full_path))
            if path_bytes >= 4096:
                problems.append(("FILE_PATH", path_bytes, str(full_path)))

            _update_progress(show_progress, current_count, total_count)

    if show_progress:
        print(f"\rСканирование: 100.0% ({current_count}/{current_count})")

    return problems, current_count


def _update_progress(show_progress, current_count, total_count):
    if show_progress and current_count % 100 == 0 and total_count > 0:
        progress = (current_count / total_count) * 100
        print(
            f"\rСканирование: {progress:.1f}% ({current_count}/{total_count})",
            end="",
            flush=True,
        )


def parse_arguments():
    class RussianFormatter(argparse.RawDescriptionHelpFormatter):
        def __init__(self, prog):
            super().__init__(prog, width=80, max_help_position=30)

        def add_usage(self, usage, actions, groups, prefix=None):
            if prefix is None:
                prefix = "Использование: "
            return super().add_usage(usage, actions, groups, prefix)

    parser = argparse.ArgumentParser(
        description="Проверка длинных путей и имен файлов для Linux",
        formatter_class=RussianFormatter,
        add_help=False,
    )

    parser.add_argument(
        "directory", nargs="?", default=".", help="Директория для проверки"
    )

    parser.add_argument(
        "-h",
        "--help",
        action="help",
        default=argparse.SUPPRESS,
        help="Показать это сообщение и выйти",
    )
    parser.add_argument(
        "-p", "--no-progress", action="store_true", help="Отключить индикатор прогресса"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Тихий режим (только цифры)"
    )
    parser.add_argument(
        "-l",
        "--log",
        nargs="?",
        const="AUTO",
        metavar="ФАЙЛ",
        help="Сохранить результаты в указанный файл (если указан без файла, используется автоматическое имя)",
    )
    parser.add_argument(
        "--axe",
        action="store_true",
        help="Автоматическое исправление длинных имён файлов/директорий. Может потребовать права root. Использовать с осторожностью!",
    )

    return parser.parse_args()


def get_auto_log_name():
    """Генерирует автоматическое имя лог-файла на основе имени текущей директории"""
    cwd = Path.cwd()
    basename = cwd.name
    if not basename:  # Если текущая директория - корневая
        basename = "root"
    return f"{basename}.LOG"


def validate_directory(directory):
    if not Path(directory).is_dir():
        print(f"Ошибка: Директория '{directory}' не существует", file=sys.stderr)
        sys.exit(1)


def write_log_report(log_file, problems, mode="a"):
    """Записывает результаты в лог-файл с возможностью дописывания"""
    with Path(log_file).open(mode, encoding="utf-8") as file:
        # Добавляем разделитель с датой и временем при дописывании
        if mode == "a":
            file.write(f"\n{'=' * 60}\n")
            file.write(f"Проверка от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            file.write(f"{'=' * 60}\n")

        if problems:
            for problem_type, length, path in problems:
                if "NAME" in problem_type:
                    file.write(f"ДЛИННОЕ ИМЯ [{length}/255]: {path}\n")
                else:
                    file.write(f"ДЛИННЫЙ ПУТЬ [{length}/4096]: {path}\n")
        else:
            file.write("Все пути и имена соответствуют ограничениям Linux\n")


def apply_fixes(problems):
    if not problems:
        print(f"{Colors.GREEN}Нет проблем для исправления{Colors.RESET}")
        return

    name_problems = [p for p in problems if "NAME" in p[0]]
    path_problems = [p for p in problems if "PATH" in p[0]]

    if path_problems:
        print(
            f"{Colors.YELLOW}Предупреждение: длинные пути не исправляются автоматически:{Colors.RESET}"
        )
        for _problem_type, length, path in path_problems:
            print(f"  ДЛИННЫЙ ПУТЬ [{length}/4096]: {path}")
        print()

    if not name_problems:
        print(f"{Colors.GREEN}Нет длинных имен для исправления{Colors.RESET}")
        return

    print(f"{Colors.BOLD}Применение исправлений к длинным именам:{Colors.RESET}")

    fixed_count = 0
    for i, (problem_type, length, path) in enumerate(name_problems, 1):
        print(f"{i}/{len(name_problems)}: {path}")

        try:
            result = fix_long_name(problem_type, length, path)
            print(f"  {Colors.GREEN}{result}{Colors.RESET}")
            fixed_count += 1
        except (OSError, shutil.Error, ValueError) as e:
            print(f"  {Colors.YELLOW}Ошибка: {e}{Colors.RESET}")

    print(
        f"{Colors.BOLD}Исправлено проблем: {fixed_count}/{len(name_problems)}{Colors.RESET}"
    )

    if path_problems:
        print(
            f"\n{Colors.YELLOW}Остались длинные пути (требуют ручного исправления): {len(path_problems)}{Colors.RESET}"
        )


def print_results(problems, total, log_file=None, quiet=False):
    if quiet:
        name_count = len([p for p in problems if "NAME" in p[0]])
        path_count = len([p for p in problems if "PATH" in p[0]])
        print(f"{name_count} {path_count} {total}")
        return

    print(f"\n{Colors.BOLD}РЕЗУЛЬТАТЫ ПРОВЕРКИ:{Colors.RESET}")
    print(f"Всего проверено: {Colors.BLUE}{total}{Colors.RESET}")

    name_problems = [p for p in problems if "NAME" in p[0]]
    path_problems = [p for p in problems if "PATH" in p[0]]

    print(
        f"Длинных имен (>255 байт): {Colors.YELLOW}{len(name_problems)}{Colors.RESET}"
    )
    print(
        f"Длинных путей (>4096 байт): {Colors.YELLOW}{len(path_problems)}{Colors.RESET}"
    )

    if problems:
        print(f"\n{Colors.BOLD}ПРОБЛЕМНЫЕ ФАЙЛЫ И ДИРЕКТОРИИ:{Colors.RESET}")
        for problem_type, length, path in problems:
            if "NAME" in problem_type:
                print(f"  ДЛИННОЕ ИМЯ [{length}/255]: {path}")
            else:
                print(f"  ДЛИННЫЙ ПУТЬ [{length}/4096]: {path}")
    else:
        print(
            f"\n{Colors.GREEN}Все пути и имена соответствуют ограничениям Linux{Colors.RESET}"
        )

    if log_file:
        print(f"\n{Colors.BLUE}Подробный отчет сохранен в: {log_file}{Colors.RESET}")


def main():
    args = parse_arguments()
    validate_directory(args.directory)

    # Определяем имя лог-файла
    log_file_name = None
    if args.log == "AUTO":
        log_file_name = get_auto_log_name()
    elif args.log is not None:
        log_file_name = args.log
    elif len(sys.argv) == 1:  # Запуск без аргументов
        log_file_name = get_auto_log_name()

    try:
        problems, total = scan_directory(args.directory, not args.no_progress)

        if args.axe:
            apply_fixes(problems)
            problems, total = scan_directory(args.directory, not args.no_progress)

        # Записываем в лог, если требуется
        if log_file_name:
            write_log_report(log_file_name, problems, "a")

        print_results(problems, total, log_file_name, args.quiet)

        sys.exit(0 if not problems else 1)

    except KeyboardInterrupt:
        print("\nПроверка прервана пользователем")
        sys.exit(1)
    except (OSError, ValueError, PermissionError) as error:
        print(f"Ошибка при выполнении: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
