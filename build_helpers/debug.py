"""
Nuitka plugin to assist with removing debug code.
"""

from string import ascii_lowercase

from nuitka.options.Options import getPositionalArgs
from nuitka.plugins.PluginBase import NuitkaPluginBase

type Slice = tuple[int, int]

START_DEBUG_ONLY = "# startdebug"
END_DEBUG_ONLY = "# enddebug"


def underline(line: str, underlined_text: str):
    if underlined_text not in line:
        return None

    whitespace = line.index(underlined_text)

    return "".join((" " * whitespace, "^" * len(underlined_text)))


class DebugProcessorPlugin(NuitkaPluginBase):
    plugin_name = "debug-code-removal-processor"

    def __init__(self):
        args: list[str] = [
            *filter(
                lambda a: any(
                    a.lower().startswith(c) for c in ascii_lowercase
                ),
                getPositionalArgs(),
            )
        ]
        if len(args) < 1:
            self.error(
                "Unexpected number of non-namespace arguments: %d", len(args)
            )
        self.target_namespace = args[0].replace(".py", "")

    def onModuleSourceCode(self, module_name, source_filename, source_code):
        name = str(module_name)

        if self.target_namespace in name or (
            self.target_namespace in source_filename
            and not ".venv" in source_filename
        ):
            source_code = self.process_debug_code(name, source_code)

        return source_code

    def process_debug_code(self, module_name: str, code: str) -> str:
        lines = code.splitlines()
        rm_lines: list[Slice] = []
        slice_current: int | None = None
        slice_end: int | None = None
        for idx, line in enumerate(lines):
            # no slice active:
            if slice_current is None:
                if line.strip() == START_DEBUG_ONLY:
                    slice_current = idx
                    continue
                elif line.strip() == END_DEBUG_ONLY:
                    err_str = f"Unexpected {END_DEBUG_ONLY} at line {idx+1}"
                    self.error(err_str)
                    err = RuntimeError(err_str)
                    err.add_note("Previous lines:")
                    start = max(idx - 10, 0) + 1
                    for n, l in enumerate(lines[max(idx - 10, 0) : idx + 1]):
                        err.add_note(f"{start + n}   {l}")
                        if n == idx:
                            if ul := underline(l, END_DEBUG_ONLY):
                                err.add_note(ul)
                    raise err
                else:
                    continue
            else:
                # active slice, looking for end
                if line.strip() == END_DEBUG_ONLY:
                    slice_end = idx
                elif line.strip() == START_DEBUG_ONLY:
                    assert slice_current is not None
                    err_str = (
                        f"Unexpected {START_DEBUG_ONLY} at line {idx+1};"
                        f"Unclosed {START_DEBUG_ONLY} at line {slice_current+1}"
                    )
                    self.error(err_str)
                    raise RuntimeError(err_str)
                else:
                    continue
            # slice start and end, append
            if not slice_current and not slice_end:
                continue
            rm_lines.append((slice_current, slice_end))
            slice_current = None
            slice_end = None
            continue

        # handle unclosed slices
        if slice_current is not None:
            err_str = f"Unclosed {START_DEBUG_ONLY} at line {slice_current+1}"
            self.error(err_str)
            raise RuntimeError(err_str)

        if not rm_lines:
            return code

        code_out = []
        rm_lines_all = set(i for s, e in rm_lines for i in range(s, e + 1))
        removing_lines: bool = False
        last_removed_line: int = -1
        for idx, line in enumerate(lines):
            if idx in rm_lines_all:
                if last_removed_line != idx - 1:
                    removing_lines = False
                if not removing_lines:
                    removing_lines = True
                last_removed_line = idx
                continue
            else:
                code_out.append(line)

        self.debug(f"Finished cleaning up {module_name}")
        return "\n".join(code_out)
