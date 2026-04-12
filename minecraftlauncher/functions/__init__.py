from xml.etree import ElementTree
import logging

class Log4jParser:
    _current_logs:list[str]
    def __init__(self):
        self._current_logs = []

    def parse_log(self, text:str):
        self._current_logs.append(text)
    
    def complete_log(self):
        log = "\n".join(self._current_logs.pop(i)
                        for i in range(len(self._current_logs)))
        el = ElementTree.fromstring(log)
        logger = el.attrib.get("logger", "<unknown logger>")
        level_raw = el.attrib.get("level", "INFO")
        if level_raw in logging._nameToLevel:
            level = logging._nameToLevel[level_raw]
        else:
            level = logging.INFO
        thread = el.attrib.get("thread", "")