"""
modes.py — the point-of-contact decision: which mode the drone and this screen go into,
decided right here in the field from the medical answers (nobody at the TOC can be asked).

    BEACON     emergency (immediate threat to life): SEVERE bleeding or breathing, or SEVERE on two or more
               life-threat questions. The drone moves to an offset position and sends the person's relative
               location to rescuers by IR / optical Morse; the person waits for a friendly signal.
    RESPONDER  urgent but not immediately life-threatening: can't walk, not safe to move, or SEVERE head wound.
               Stay put; the drone flies straight back to the TOC to update the rescue team.
    ESCORT     can walk AND safe to move (both OK or FINE): the drone leads the person out at walking pace

Priority: BEACON > RESPONDER > ESCORT. A skipped answer is treated as the worse case.
"""

ESCORT, RESPONDER, BEACON = "ESCORT", "RESPONDER", "BEACON"
SWITCH_TO_RESPONDER = "switch_responder"     # page action: escort aborted ("I'm hurt")

# Question order (content.py): bleeding, breathing, head, cold, walk, arms, safe_to_move
BLEEDING, BREATHING, HEAD, COLD, WALK, ARMS, SAFE_TO_MOVE = range(7)
SEVERE, BAD, OK, FINE = 0, 1, 2, 3

WALKING_SPEED_MPS = 0.8          # a tired person on rough ground
BEACON_OFFSET_M = 200            # the beacon drone hovers this far from the person, toward the rescue team
FRIENDLY_SIGNAL_TEXT = "3 short flashes or 3 whistles"
FRIENDLY_SIGNAL_COUNT = 3
ANSWER_TEXT = "Answer with 3 whistles or 3 taps"
TEAM_SPEED_MPS = 1.2             # a rescue team on foot

MODE_STYLE = {
    #           title                  header color      accent
    ESCORT:    ("ESCORT MODE",        (30, 130, 70),    (60, 200, 110)),
    RESPONDER: ("HELP IS COMING",     (190, 120, 10),   (255, 180, 40)),
    BEACON:    ("EMERGENCY BEACON",   (180, 20, 25),    (255, 70, 70)),
}


def decide_mode(values):
    """Return (mode, reason) from the 7 answers. values: list of 0-3 or None."""
    def is_severe(index):
        return values[index] == SEVERE

    def is_bad_or_worse(index):
        return values[index] is None or values[index] <= BAD

    life_threats = [index for index in (BLEEDING, BREATHING, HEAD, COLD) if is_severe(index)]
    if is_severe(BLEEDING) or is_severe(BREATHING) or len(life_threats) >= 2:
        names = {BLEEDING: "bleeding", BREATHING: "breathing", HEAD: "head wound", COLD: "cold"}
        return BEACON, "SEVERE " + ", ".join(names[index] for index in life_threats)
    if is_bad_or_worse(WALK):
        return RESPONDER, "cannot walk" if values[WALK] is not None else "walking unknown"
    if is_bad_or_worse(SAFE_TO_MOVE):
        return RESPONDER, "not safe to move"
    if is_severe(HEAD):
        return RESPONDER, "SEVERE head wound"
    return ESCORT, "can walk, safe to move"


MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.", "G": "--.", "H": "....",
    "I": "..", "J": ".---", "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---", "P": ".--.",
    "Q": "--.-", "R": ".-.", "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..", "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
}


def morse_timeline(message):
    """
    Turn a message into on/off steps, in Morse time units:
    dot = 1 on, dash = 3 on, gap inside a letter = 1 off, between letters = 3 off, between words = 7 off.
    Returns a list of (is_on, units, letter_index).
    """
    steps = []
    words = message.upper().split()
    letter_index = 0
    for word_number, word in enumerate(words):
        for letter_number, letter in enumerate(word):
            code = MORSE.get(letter, "")
            for symbol_number, symbol in enumerate(code):
                steps.append((True, 1 if symbol == "." else 3, letter_index))
                if symbol_number < len(code) - 1:
                    steps.append((False, 1, letter_index))
            if letter_number < len(word) - 1:
                steps.append((False, 3, letter_index))
            letter_index += 1
        steps.append((False, 7, letter_index - 1))       # word gap; also the pause before repeating
    return steps


def beacon_message(map_state, compass_word):
    """
    What the beacon drone sends: SOS plus where the person is relative to the beacon.
    The drone hovers BEACON_OFFSET_M toward the rescue team, so the person is in the opposite direction
    from it, e.g. "SOS SW 200" = the casualty is 200 m south-west of this light.
    Returns (message, drone_bearing_from_person) or ("SOS", None) when the team position is unknown.
    """
    team = map_state.team()
    if team is None:
        return "SOS", None
    toward_team = map_state.bearing_deg(team)
    person_from_beacon = compass_word((toward_team + 180) % 360)
    return f"SOS {person_from_beacon} {BEACON_OFFSET_M}", toward_team
