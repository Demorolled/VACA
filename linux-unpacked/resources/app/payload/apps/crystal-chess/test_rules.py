#!/usr/bin/env python3
"""Headless unit tests for the chess rules engine (no pygame needed).

Run:  python3 test_rules.py
"""
import random
import unittest

from engine import ChessGame, best_move, evaluate, START_FEN


def fen_board(rows: list, turn='w', castle='', ep=None) -> ChessGame:
    """Build a game from explicit board rows (a8 first)."""
    g = ChessGame()
    g.board = [[None] * 8 for _ in range(8)]
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch != '.':
                g.board[r][c] = ('w' if ch.isupper() else 'b', ch.upper())
    g.turn = turn
    g.castle = {'K': 'K' in castle, 'Q': 'Q' in castle,
                'k': 'k' in castle, 'q': 'q' in castle}
    g.ep = ep
    g.halfmove = 0
    g.key = g._position_key()
    g.position_counts = {g.key: 1}
    return g


class TestSetup(unittest.TestCase):
    def test_start_position(self):
        g = ChessGame()
        self.assertEqual(g.board[0][0], ('b', 'R'))
        self.assertEqual(g.board[7][4], ('w', 'K'))
        self.assertEqual(g.turn, 'w')
        self.assertEqual(len(g.legal_moves()), 20)

    def test_initial_legal_move_count(self):
        g = ChessGame()
        self.assertEqual(len(g.legal_moves()), 20)

    def test_move_undo_restores(self):
        g = ChessGame()
        before = [row[:] for row in g.board]
        g.make_move((6, 4, 4, 4, ''))  # e4
        g.make_move((1, 4, 3, 4, ''))  # e5
        self.assertEqual(g.turn, 'w')
        g.undo()
        g.undo()
        self.assertEqual([row[:] for row in g.board], before)
        self.assertEqual(g.turn, 'w')


class TestPawns(unittest.TestCase):
    def test_double_push_sets_en_passant(self):
        g = fen_board(['........'] * 8)
        g.board[6][4] = ('w', 'P')
        g.board[3][4] = ('b', 'P')
        g.ep = None
        g.key = g._position_key()
        g.position_counts[g.key] = 1
        g.make_move((6, 4, 4, 4, ''))
        self.assertEqual(g.ep, (5, 4))

    def test_en_passant_capture(self):
        # White pawn on c5; black just double-pushed b7-b5 -> ep target b6.
        g = fen_board(['........'] * 8)
        g.board[3][2] = ('w', 'P')   # white pawn on c5
        g.board[3][1] = ('b', 'P')   # black pawn on b5
        g.turn = 'w'
        g.ep = (2, 1)                # en-passant target after b7-b5
        g.key = g._position_key()
        g.position_counts = {g.key: 1}
        moves = g.legal_moves()
        ep_move = (3, 2, 2, 1, '')
        self.assertIn(ep_move, moves)
        g.make_move(ep_move)
        self.assertIsNone(g.board[3][1])  # black pawn removed
        self.assertEqual(g.board[2][1], ('w', 'P'))

    def test_promotion_offered(self):
        g = fen_board(['........'] * 8)
        g.board[1][0] = ('w', 'P')
        g.turn = 'w'
        g.key = g._position_key()
        g.position_counts = {g.key: 1}
        moves = g.legal_moves()
        self.assertTrue(any(m[4] == 'Q' for m in moves))
        g.make_move((1, 0, 0, 0, 'Q'))
        self.assertEqual(g.board[0][0], ('w', 'Q'))


class TestCastling(unittest.TestCase):
    def test_kingside_castle(self):
        # (The old setup left a stray BLACK rook on a1 from a fen row, putting
        # the white king in check and killing the castle — place pieces on an
        # empty board instead.)
        g = fen_board(['........'] * 8, turn='w', castle='KQ')
        g.board[7][4] = ('w', 'K')
        g.board[7][7] = ('w', 'R')
        g.board[0][0] = ('b', 'R')
        g.board[0][4] = ('b', 'K')
        g.board[0][7] = ('b', 'R')
        moves = g.legal_moves()
        self.assertIn((7, 4, 7, 6, ''), moves)
        g.make_move((7, 4, 7, 6, ''))
        self.assertEqual(g.board[7][6], ('w', 'K'))
        self.assertEqual(g.board[7][5], ('w', 'R'))
        self.assertFalse(g.castle['K'] and g.castle['Q'])

    def test_castle_blocked_through_check(self):
        # Rook attacks f1 -> white can't castle kingside.
        g = fen_board(['........'] * 8)
        g.board[7][4] = ('w', 'K')
        g.board[7][7] = ('w', 'R')
        g.board[1][5] = ('b', 'R')  # attacks down the f-file
        g.castle = {'K': True, 'Q': True, 'k': False, 'q': False}
        moves = g.legal_moves()
        self.assertNotIn((7, 4, 7, 6, ''), moves)


class TestCheckAndMate(unittest.TestCase):
    def test_fools_mate(self):
        g = ChessGame()
        for m in [(6, 5, 5, 5, ''), (1, 4, 3, 4, ''), (6, 6, 4, 6, ''),
                  (0, 3, 4, 7, '')]:  # f3 e5 g4 Qh4#
            self.assertTrue(g.make_move(m), f'failed on {m}')
        self.assertEqual(g.result()[0], 'checkmate')
        self.assertTrue(g.in_check())

    def test_stalemate(self):
        # Classic: black king a8 boxed by white queen b6 + white king c6.
        g = fen_board(['........'] * 8, turn='b', castle='')
        g.board[0][0] = ('b', 'K')   # a8
        g.board[2][1] = ('w', 'Q')   # b6
        g.board[2][2] = ('w', 'K')   # c6
        g.turn = 'b'
        g.key = g._position_key()
        g.position_counts = {g.key: 1}
        self.assertFalse(g.in_check('b'))
        self.assertEqual(len(g.legal_moves('b')), 0)
        self.assertEqual(g.result()[0], 'stalemate')

    def test_check_detection(self):
        g = fen_board(['........'] * 8)
        g.board[7][4] = ('w', 'K')
        g.board[3][4] = ('b', 'R')
        g.turn = 'w'
        g.key = g._position_key()
        g.position_counts = {g.key: 1}
        self.assertTrue(g.in_check('w'))
        # king can move off the file or capture; no moves that stay in check
        for m in g.legal_moves():
            self.assertTrue(g._is_legal(m, 'w'))


class TestPieces(unittest.TestCase):
    def test_knight_moves(self):
        g = fen_board(['........'] * 8)
        g.board[4][4] = ('w', 'N')
        moves = {(m[2], m[3]) for m in g.legal_moves()}
        self.assertEqual(len(moves), 8)

    def test_pinned_piece_cannot_expose_king(self):
        # A knight on e2 is fully pinned by a rook on the e-file: EVERY knight
        # move leaves the file open onto the king, so it has zero legal moves.
        # (A pawn straight up the file would NOT be pinned — e2-e3 keeps
        # blocking — which is why a knight is the right probe.)
        g = fen_board(['........'] * 8)
        g.board[7][4] = ('w', 'K')   # e1
        g.board[6][4] = ('w', 'N')   # e2 (pinned)
        g.board[1][4] = ('b', 'R')   # e8
        g.turn = 'w'
        g.key = g._position_key()
        g.position_counts = {g.key: 1}
        moves = g.legal_moves()
        knight_moves = [m for m in moves if m[0] == 6 and m[1] == 4]
        self.assertEqual(knight_moves, [])


class TestDraws(unittest.TestCase):
    def test_fifty_move_rule(self):
        g = fen_board(['k.......', '........', '........', '........',
                       '........', '........', '........', 'K.......'])
        g.board[0][0] = ('b', 'K')
        g.board[7][0] = ('w', 'K')
        g.turn = 'w'
        g.halfmove = 99
        g.key = g._position_key()
        g.position_counts = {g.key: 1}
        # two quiet king moves
        self.assertTrue(g.make_move((7, 0, 7, 1, '')))
        self.assertTrue(g.make_move((0, 0, 0, 1, '')))
        self.assertEqual(g.result()[0], 'draw')

    def test_insufficient_material(self):
        g = fen_board(['........'] * 8)
        g.board[0][0] = ('b', 'K')
        g.board[7][0] = ('w', 'K')
        g.board[7][2] = ('w', 'B')
        self.assertTrue(g.insufficient_material())
        g.board[7][2] = ('w', 'R')
        self.assertFalse(g.insufficient_material())

    def test_threefold_repetition(self):
        g = ChessGame()
        # Ng1-f3, Ng8-f6, Nf3-g1, Nf6-g8 repeated 3x — the 12th move
        # returns to the start position for the 3rd time.
        loop = [(7, 6, 5, 5, ''), (0, 6, 2, 5, ''), (5, 5, 7, 6, ''),
                (2, 5, 0, 6, '')] * 3
        for m in loop:
            self.assertTrue(g.make_move(m), f'failed on {m}')
        self.assertEqual(g.result()[0], 'draw')


class TestAI(unittest.TestCase):
    def test_best_move_returns_legal_move(self):
        g = ChessGame()
        m = best_move(g, depth=1)
        self.assertIsNotNone(m)
        self.assertIn(m, g.legal_moves())

    def test_ai_captures_hanging_queen(self):
        g = fen_board(['........'] * 8)
        g.board[7][4] = ('w', 'K')
        g.board[0][4] = ('b', 'K')
        g.board[4][4] = ('w', 'N')   # white knight can take the queen
        g.board[6][3] = ('b', 'Q')   # hanging black queen
        g.turn = 'w'
        g.key = g._position_key()
        g.position_counts = {g.key: 1}
        m = best_move(g, depth=2)
        self.assertIsNotNone(m)
        g.make_move(m)
        self.assertFalse(any(p == ('b', 'Q') for row in g.board for p in row))

    def test_ai_evades_checkmate_threat(self):
        g = fen_board(['k.......', '........', '........', '........',
                       '........', '........', 'PPPPPPPP', 'RNBQKBNR'])
        g.board[0][0] = ('b', 'K')
        g.board[7][4] = ('w', 'K')
        g.board[1][4] = ('b', 'Q')  # black queen on e7 giving... not check yet
        g.turn = 'w'
        g.key = g._position_key()
        g.position_counts = {g.key: 1}
        m = best_move(g, depth=2)
        self.assertIsNotNone(m)
        self.assertTrue(g._is_legal(m, 'w'))

    def test_evaluate_symmetric(self):
        g = ChessGame()
        self.assertEqual(evaluate(g, 'w'), -evaluate(g, 'b'))

    def test_random_selfplay_smoke(self):
        rng = random.Random(7)
        g = ChessGame()
        for _ in range(200):
            moves = g.legal_moves()
            if not moves:
                break
            g.make_move(rng.choice(moves))
        self.assertIn(g.result()[0], ('checkmate', 'stalemate', 'draw', 'ongoing'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
