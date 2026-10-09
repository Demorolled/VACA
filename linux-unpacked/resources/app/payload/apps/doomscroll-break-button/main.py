"""
Doomscroll Break Button — the offline, one-click break from doomscrolling.

A single big button. Press it, get a random tiny action, do it. No login,
no accounts, no internet. Inspired by "Ugh Okay"
(https://maxbasev.com/blog/build/ugh-okay).

Run:  python3 main.py
"""

import random
import tkinter as tk

ACTIONS = [
    "Stretch for 2 minutes — arms up, side to side.",
    "Stand up and take 10 slow breaths.",
    "Drink a glass of water.",
    "Look out a window at something far away for 60 seconds.",
    "Do 5 squats or 10 jumping jacks.",
    "Read one page of a real book.",
    "Tidy exactly one small surface (desk corner, one drawer).",
    "Text or call someone you've been meaning to reach.",
    "Write down the one thing you actually wanted to do today.",
    "Take a 5-minute walk — even just around the room.",
    "Make a cup of tea or coffee and actually taste it.",
    "Close your eyes and name 5 things you can hear.",
    "Do one tiny task you've been avoiding (under 2 minutes).",
    "Stand, roll your shoulders, and look up for 30 seconds.",
]

WINDOW_BG = "#0d1117"
BUTTON_BG = "#2ea043"
BUTTON_ACTIVE = "#238636"
TEXT_FG = "#e6edf3"
ACTION_FG = "#58a6ff"


class BreakButton:
    def __init__(self, root: tk.Tk):
        root.title("Doomscroll Break Button")
        root.configure(bg=WINDOW_BG)
        root.geometry("520x420")
        root.minsize(420, 360)

        prompt = tk.Label(root, text="Feeling stuck in the scroll?",
                          font=("Helvetica", 16), bg=WINDOW_BG, fg=TEXT_FG)
        prompt.pack(pady=(24, 8))

        self.action_label = tk.Label(
            root, text="Press the button.", wraplength=440, justify="center",
            font=("Helvetica", 15, "bold"), bg=WINDOW_BG, fg=ACTION_FG, height=4)
        self.action_label.pack(pady=8, padx=16)

        self.break_btn = tk.Button(
            root, text="BREAK", font=("Helvetica", 22, "bold"),
            bg=BUTTON_BG, fg="white", activebackground=BUTTON_ACTIVE,
            activeforeground="white", relief="flat", bd=0,
            width=12, height=2, cursor="hand2",
            command=self.give_action)
        self.break_btn.pack(pady=16)

        self.next_btn = tk.Button(
            root, text="Done — give me another", font=("Helvetica", 12),
            bg=WINDOW_BG, fg=TEXT_FG, relief="flat", bd=0, cursor="hand2",
            command=self.give_action, state="disabled")
        self.next_btn.pack(pady=4)

        tip = tk.Label(root, text="No accounts. No tracking. No internet.",
                       font=("Helvetica", 10), bg=WINDOW_BG, fg="#8b949e")
        tip.pack(side="bottom", pady=12)

    def give_action(self):
        self.action_label.config(text=random.choice(ACTIONS))
        self.next_btn.config(state="normal")


def main():
    root = tk.Tk()
    BreakButton(root)
    root.mainloop()


if __name__ == "__main__":
    main()
