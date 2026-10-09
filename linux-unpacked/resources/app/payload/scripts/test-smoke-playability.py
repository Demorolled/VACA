#!/usr/bin/env python3
"""
Tests for the playability probe in smoke-test-html.py (the board-game gate).

The probe must:
  - PASS a board whose pieces can actually move (legal-move targets appear,
    pieces relocate on destination click) — the rebuilt chess game.
  - FAIL a board that renders clickable pieces but has NO move logic — the
    "static board" class that shipped for the chess build ("renders, but you
    can never move a piece").
  - SKIP pages with no board-like container (>= 8 clickable non-control cells)
    so normal apps / static pages are unaffected.

Run: python3 -m pytest scripts/test-smoke-playability.py -v
(skips automatically when playwright or the system Chrome is unavailable)
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SMOKE = os.path.join(HERE, "smoke-test-html.py")

pytest = None
try:
    import pytest
except ImportError:
    pytest = None

try:
    from playwright.sync_api import sync_playwright  # noqa: F401
    import shutil
    _PLAYWRIGHT = True
except ImportError:
    _PLAYWRIGHT = False

_CHROME = "/usr/bin/google-chrome"
_CHROME_OK = os.path.isfile(_CHROME)

REQUIRED = _PLAYWRIGHT and _CHROME_OK and pytest is not None


def _run_smoke(html_path, wait=1500):
    proc = subprocess.run(
        [sys.executable, SMOKE, os.path.abspath(html_path), "--behavioral", "--wait", str(wait)],
        capture_output=True, text=True, cwd=ROOT,
    )
    out = proc.stdout.strip()
    try:
        return json.loads(out), proc.returncode
    except json.JSONDecodeError:
        return {"parse_error": out[-2000:]}, proc.returncode


def _playable_html():
    """A minimal playable board: clicking a piece shows move targets and a
    destination click relocates the piece (a real move), like the rebuilt game."""
    return """<!DOCTYPE html><html><head><style>
      #board { position: relative; width: 280px; height: 280px; margin: 20px auto; }
      .square { position: absolute; width: 70px; height: 70px; cursor: pointer; box-sizing: border-box; }
      .square.light { background: #f0d9b5; } .square.dark { background: #b58863; }
      .piece { position: absolute; width: 70px; height: 70px; font-size: 40px; text-align: center; line-height: 70px; cursor: pointer; }
      .target { outline: 3px solid #2a6df4; }
      .piece.selected { outline: 3px solid gold; }
    </style></head><body><div id="board"></div><div id="status">White to move</div>
    <script>
      const board = document.getElementById('board');
      const state = { selected: null, moves: [] };
      // 4x4 board: 16 squares, 4 movable pieces.
      for (let i = 0; i < 16; i++) {
        const sq = document.createElement('div');
        sq.className = 'square ' + (i % 2 ? 'dark' : 'light');
        sq.style.left = (i % 4) * 70 + 'px';
        sq.style.top = Math.floor(i / 4) * 70 + 'px';
        sq.addEventListener('click', () => {
          document.querySelectorAll('.target').forEach(t => t.classList.remove('target'));
          if (state.selected !== null) {
            // destination click: if the square is a marked target, MOVE there
            if (sq.classList.contains('target')) {
              const p = document.querySelector('.piece.selected');
              p.style.left = sq.style.left; p.style.top = sq.style.top;
              document.getElementById('status').textContent = 'moved';
            }
            state.selected = null;
            document.querySelectorAll('.piece.selected').forEach(x => x.classList.remove('selected'));
            return;
          }
          // select a piece on this square
          const piece = sq.querySelector('.piece');
          if (piece) {
            state.selected = piece;
            piece.classList.add('selected');
            // mark the 2 squares below as legal targets
            const i = [...board.children].indexOf(sq);
            const below = [i + 4, i + 5];
            below.forEach(j => { const t = board.children[j]; if (t) t.classList.add('target'); });
          }
        });
        board.appendChild(sq);
      }
      ['P', 'Q', 'R', 'N'].forEach((p, i) => {
        const el = document.createElement('div');
        el.className = 'piece';
        el.textContent = p;
        el.style.left = (i % 4) * 70 + 'px';
        el.style.top = '0px';
        board.children[i].appendChild(el);
      });
    </script></body></html>"""


def _static_board_html():
    """The exact broken class: pieces can be SELECTED (class toggles, status
    text changes) but there is NO move logic — clicking anywhere never
    relocates anything and no legal-move markers ever appear."""
    return """<!DOCTYPE html><html><head><style>
      #board { position: relative; width: 280px; height: 280px; margin: 20px auto; }
      .square { position: absolute; width: 70px; height: 70px; cursor: pointer; }
      .square.light { background: #f0d9b5; } .square.dark { background: #b58863; }
      .piece { position: absolute; width: 70px; height: 70px; font-size: 40px; text-align: center; cursor: pointer; }
      .selected { outline: 3px solid gold; }
    </style></head><body>
    <div id="board"></div>
    <div id="statusMsg">Click a piece</div>
    <script>
      const board = document.getElementById('board');
      for (let i = 0; i < 16; i++) {
        const sq = document.createElement('div');
        sq.className = 'square ' + (i % 2 ? 'dark' : 'light');
        sq.style.left = (i % 4) * 70 + 'px';
        sq.style.top = Math.floor(i / 4) * 70 + 'px';
        board.appendChild(sq);
      }
      ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R'].forEach((p, i) => {
        const el = document.createElement('div');
        el.className = 'piece';
        el.textContent = p;
        el.style.left = (i % 4) * 70 + 'px';
        el.style.top = '0px';
        el.onclick = () => {
          document.querySelectorAll('.piece').forEach(x => x.classList.remove('selected'));
          el.classList.add('selected');
          document.getElementById('statusMsg').textContent = 'Selected: ' + el.textContent;
        };
        board.appendChild(el);
      });
      // NOTE: no destination click handler — pieces can never move.
    </script></body></html>"""


def _empty_cell_game_html():
    """An empty-board game like tic-tac-toe: cells start EMPTY (no pieces),
    but clicking a cell places a mark — a real state change. The probe must
    NOT treat "0 occupied cells" as static; it must click empty cells."""
    return """<!DOCTYPE html><html><head><style>
      #board { display: grid; grid-template-columns: repeat(3, 80px); gap: 4px; }
      .cell { width: 80px; height: 80px; background: #ddd; cursor: pointer; font-size: 40px; display: flex; align-items: center; justify-content: center; }
    </style></head><body><div id="board"></div>
    <script>
      const board = document.getElementById('board');
      let turn = 'X';
      for (let i = 0; i < 9; i++) {
        const c = document.createElement('div');
        c.className = 'cell';
        c.addEventListener('click', () => {
          if (c.textContent) return;
          c.textContent = turn;
          turn = turn === 'X' ? 'O' : 'X';
        });
        board.appendChild(c);
      }
    </script></body></html>"""


def _colored_piece_game_html():
    """A checkers-style game: pieces are COLORED DIVS with NO text (so the
    text-layout fingerprint sees nothing) and legal moves are to adjacent
    cells with NO marker classes (targets highlighted via transform). The
    probe must detect playability by tracking the piece ELEMENT's own
    position across clicks."""
    return """<!DOCTYPE html><html><head><style>
      #board { position: relative; width: 280px; height: 280px; margin: 20px auto; }
      .square { position: absolute; width: 70px; height: 70px; cursor: pointer; }
      .square.light { background: #f0d9b5; } .square.dark { background: #b58863; }
      .piece { position: absolute; width: 50px; height: 50px; border-radius: 50%; left: 10px; top: 10px; }
      .red { background: #d22; } .black { background: #222; }
    </style></head><body><div id="board"></div><div id="status">red to move</div>
    <script>
      const board = document.getElementById('board');
      const ROWS = 4, COLS = 4;
      let selected = null;
      let turn = 'red';
      for (let r = 0; r < ROWS; r++) {
        for (let c = 0; c < COLS; c++) {
          const sq = document.createElement('div');
          sq.className = 'square ' + ((r + c) % 2 ? 'dark' : 'light');
          sq.style.left = c * 70 + 'px';
          sq.style.top = r * 70 + 'px';
          sq.dataset.row = r; sq.dataset.col = c;
          sq.addEventListener('click', () => {
            if (selected && selected.dataset !== sq.dataset) {
              const pr = +selected.dataset.row, pc = +selected.dataset.col;
              const dr = +sq.dataset.row, dc = +sq.dataset.col;
              // diagonal single step to an empty square
              if (Math.abs(dr - pr) === 1 && Math.abs(dc - pc) === 1 && !sq.firstElementChild) {
                sq.appendChild(selected.firstElementChild);
                selected = null;
                turn = turn === 'red' ? 'black' : 'red';
                document.getElementById('status').textContent = turn + ' to move';
                return;
              }
            }
            const piece = sq.firstElementChild;
            if (piece && piece.classList.contains(turn)) {
              selected = sq;
              piece.style.transform = 'scale(1.2)';
            } else {
              selected = null;
            }
          });
          board.appendChild(sq);
        }
      }
      // pieces on the back two rows, no text
      [[0,1],[0,3],[1,0],[1,2]].forEach(([r, c]) => {
        const p = document.createElement('div');
        p.className = 'piece red';
        board.children[r * COLS + c].appendChild(p);
      });
      [[2,1],[2,3],[3,0],[3,2]].forEach(([r, c]) => {
        const p = document.createElement('div');
        p.className = 'piece black';
        board.children[r * COLS + c].appendChild(p);
      });
    </script></body></html>"""


def _static_colored_board_html():
    """Colored-div pieces that can be SELECTED (transform toggles) but NEVER
    move — the static class for textless piece games. The probe must fail it
    despite the selection transform, which changes computed style but not the
    piece's position."""
    return """<!DOCTYPE html><html><head><style>
      #board { position: relative; width: 280px; height: 280px; margin: 20px auto; }
      .square { position: absolute; width: 70px; height: 70px; cursor: pointer; }
      .square.light { background: #f0d9b5; } .square.dark { background: #b58863; }
      .piece { position: absolute; width: 50px; height: 50px; border-radius: 50%; left: 10px; top: 10px; }
      .red { background: #d22; } .black { background: #222; }
    </style></head><body><div id="board"></div><div id="status">Click a piece</div>
    <script>
      const board = document.getElementById('board');
      for (let i = 0; i < 16; i++) {
        const sq = document.createElement('div');
        sq.className = 'square ' + (i % 2 ? 'dark' : 'light');
        sq.style.left = (i % 4) * 70 + 'px';
        sq.style.top = Math.floor(i / 4) * 70 + 'px';
        board.appendChild(sq);
      }
      // clickable colored pieces that only toggle a transform — never move
      [[0,1],[0,3],[1,0],[1,2]].forEach(([r, c]) => {
        const p = document.createElement('div');
        p.className = 'piece red';
        p.style.left = c * 70 + 10 + 'px'; p.style.top = r * 70 + 10 + 'px';
        p.onclick = () => {
          document.querySelectorAll('.piece').forEach(x => x.style.transform = '');
          p.style.transform = 'scale(1.2)';
          document.getElementById('status').textContent = 'selected';
        };
        board.appendChild(p);
      });
    </script></body></html>"""


def _static_empty_board_html():
    """Empty cells that do NOTHING on click — no mark ever appears. The static
    class for empty-cell boards."""
    return """<!DOCTYPE html><html><head><style>
      #board { display: grid; grid-template-columns: repeat(3, 80px); gap: 4px; }
      .cell { width: 80px; height: 80px; background: #ddd; cursor: pointer; }
    </style></head><body><div id="board"></div>
    <script>
      const board = document.getElementById('board');
      for (let i = 0; i < 9; i++) {
        const c = document.createElement('div');
        c.className = 'cell';
        c.addEventListener('click', () => {});
        board.appendChild(c);
      }
    </script></body></html>"""


def _plain_page_html():
    return """<!DOCTYPE html><html><head><title>Info</title></head><body>
    <h1>Welcome</h1><p>A normal page.</p>
    <ul><li>one</li><li>two</li><li>three</li></ul>
    <a href="https://example.com">More</a>
    </body></html>"""


def _truncated_script_html():
    """A board game CUT OFF mid-generation: the <script> block is never closed
    and </body>/</html> are missing (the file simply ends at the token cap).
    This is the smoke gate's worst blind spot: Chrome silently swallows the
    unclosed <script> (no pageerror), the board never renders, and the
    playability probe reports "no board-like container" → the truncated file
    would PASS. The truncation check must fail it with an explicit detail."""
    return ("<!DOCTYPE html><html><head><style>"
            ".cell { width: 50px; height: 50px; cursor: pointer; }"
            "</style></head><body><div id=\"board\"></div>"
            "<button id=\"restart\">Restart</button>"
            "<script>"
            "const board = document.getElementById('board');"
            "for (let i = 0; i < 8; i++) {"
            "  const cell = document.createElement('div');"
            "  cell.classList.")


def _truncated_missing_html_close():
    """A page that IS closed internally (</script></body> present) but never
    closes </html> — still a truncation (the file ends before its natural
    end), and must fail even though Chrome renders it fine."""
    return ("<!DOCTYPE html><html><body><div id=\"board\"></div>"
            "<button id=\"go\">Go</button>"
            "<script>document.getElementById('board').textContent = 'hi';"
            "</script></body>")


def _complete_plain_html():
    """Control: a structurally complete document must NOT be flagged as
    truncated (missing-tag check must not false-positive on valid HTML)."""
    return ("<!DOCTYPE html><html><body><div id=\"board\"></div>"
            "<button id=\"go\">Go</button>"
            "<script>document.getElementById('board').textContent = 'hi';"
            "</script></body></html>")


if not REQUIRED:
    print("SKIP: playwright or /usr/bin/google-chrome or pytest unavailable")
    if pytest is not None:
        pytest.skip("playwright / chrome / pytest unavailable", allow_module_level=True)
    sys.exit(0)


def _write_tmp(name, content):
    path = os.path.join("/tmp", f"probe-{os.getpid()}-{name}")
    with open(path, "w") as fh:
        fh.write(content)
    return path


@pytest.fixture(scope="module")
def playable_html():
    return _write_tmp("playable.html", _playable_html())


@pytest.fixture(scope="module")
def static_board_html():
    return _write_tmp("static.html", _static_board_html())


@pytest.fixture(scope="module")
def plain_page_html():
    return _write_tmp("plain.html", _plain_page_html())


@pytest.fixture(scope="module")
def empty_cell_game_html():
    return _write_tmp("emptygame.html", _empty_cell_game_html())


@pytest.fixture(scope="module")
def static_empty_board_html():
    return _write_tmp("staticempty.html", _static_empty_board_html())


@pytest.fixture(scope="module")
def colored_piece_game_html():
    return _write_tmp("coloredgame.html", _colored_piece_game_html())


@pytest.fixture(scope="module")
def static_colored_board_html():
    return _write_tmp("staticcolored.html", _static_colored_board_html())


@pytest.fixture(scope="module")
def truncated_script_html():
    return _write_tmp("truncscript.html", _truncated_script_html())


@pytest.fixture(scope="module")
def truncated_missing_html_close():
    return _write_tmp("truncnoclose.html", _truncated_missing_html_close())


@pytest.fixture(scope="module")
def complete_plain_html():
    return _write_tmp("complete.html", _complete_plain_html())


def test_playable_board_passes(playable_html):
    result, code = _run_smoke(playable_html)
    assert result.get("pass") is True, json.dumps(result, indent=1)
    assert result["behavioral"]["playability"]["playable"] is True
    assert result["behavioral"]["playability"]["detected"] is True


def test_static_board_fails(static_board_html):
    result, code = _run_smoke(static_board_html)
    assert result.get("pass") is False, json.dumps(result, indent=1)
    assert result["behavioral"]["playability"]["detected"] is True
    assert result["behavioral"]["playability"]["playable"] is False
    assert result["behavioral"]["playability"]["targetsAppeared"] is False
    assert result["behavioral"]["playability"]["piecesMoved"] is False


def test_plain_page_skips_probe(plain_page_html):
    result, code = _run_smoke(plain_page_html)
    # Plain page has no board → probe does not fire, page still passes.
    assert result.get("pass") is True, json.dumps(result, indent=1)
    assert result["behavioral"]["playability"]["detected"] is False


def test_empty_cell_game_passes(empty_cell_game_html):
    # Tic-tac-toe-style: no pieces at start, but clicking a cell places a mark.
    result, code = _run_smoke(empty_cell_game_html)
    assert result.get("pass") is True, json.dumps(result, indent=1)
    play = result["behavioral"]["playability"]
    assert play["playable"] is True
    assert play["piecesMoved"] is True


def test_static_empty_board_fails(static_empty_board_html):
    # Empty cells that do nothing on click — must fail.
    result, code = _run_smoke(static_empty_board_html)
    assert result.get("pass") is False, json.dumps(result, indent=1)
    play = result["behavioral"]["playability"]
    assert play["playable"] is False
    assert play["piecesMoved"] is False


def test_colored_piece_game_passes(colored_piece_game_html):
    # Checkers-style: colored-div pieces (no text), moves to adjacent cells
    # with no marker classes — detected by tracking the piece element's own
    # position.
    result, code = _run_smoke(colored_piece_game_html)
    assert result.get("pass") is True, json.dumps(result, indent=1)
    play = result["behavioral"]["playability"]
    assert play["playable"] is True
    assert play["piecesMoved"] is True


def test_static_colored_board_fails(static_colored_board_html):
    # Colored pieces that only toggle a transform on select — never relocate.
    # The selection transform changes computed style but NOT the piece's
    # position, so the element-tracking probe must still fail it.
    result, code = _run_smoke(static_colored_board_html)
    assert result.get("pass") is False, json.dumps(result, indent=1)
    play = result["behavioral"]["playability"]
    assert play["playable"] is False
    assert play["piecesMoved"] is False


def test_truncated_script_fails(truncated_script_html):
    # The critical blind spot: a file cut off mid-<script> (no closing tags)
    # loads with NO pageerror, the board never renders, and the playability
    # probe sees "no board" — the old gate PASSED it. The truncation check
    # must fail it with an explicit TRUNCATION detail.
    result, code = _run_smoke(truncated_script_html)
    assert result.get("pass") is False, json.dumps(result, indent=1)
    trunc = result.get("truncation") or {}
    assert trunc.get("truncated") is True, json.dumps(result, indent=1)
    assert "unclosed <script>" in (trunc.get("detail") or "")
    assert "</html>" in (trunc.get("detail") or "") or "</body>" in (trunc.get("detail") or "")


def test_truncated_missing_html_close_fails(truncated_missing_html_close):
    # Script/body are closed but </html> is missing — the file still ends
    # before its natural end. Must fail (Chrome would render it fine, which is
    # exactly why the source check is needed).
    result, code = _run_smoke(truncated_missing_html_close)
    assert result.get("pass") is False, json.dumps(result, indent=1)
    trunc = result.get("truncation") or {}
    assert trunc.get("truncated") is True, json.dumps(result, indent=1)
    assert "</html>" in (trunc.get("detail") or "")


def test_complete_html_not_flagged(complete_plain_html):
    # Control: a structurally complete document must pass and NOT be flagged
    # as truncated (no false positives on valid HTML).
    result, code = _run_smoke(complete_plain_html)
    assert result.get("pass") is True, json.dumps(result, indent=1)
    trunc = result.get("truncation") or {}
    assert trunc.get("truncated") is False, json.dumps(result, indent=1)
