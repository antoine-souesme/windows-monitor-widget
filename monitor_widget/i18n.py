# -*- coding: utf-8 -*-
"""Language of the user facing texts.

The texts are written in French in the code and translated at display time
with `tr()`: the French text is its own key, so a missing translation simply
shows the French one instead of failing.
"""

# Code and name of each language, the name written in the language itself.
LANGUAGES = [("en", "English"), ("fr", "Français")]
DEFAULT = "en"

ENGLISH = {
    # Widget and context menu
    "Options…": "Options…",
    "Quitter": "Quit",
    "Veuillez sélectionner une métrique à afficher":
        "Please select a metric to display",
    # Notification area
    "Afficher le widget": "Show the widget",
    # Options window
    "Affichage": "Display",
    "Normal": "Normal",
    "Compact": "Compact",
    "Personnalisé": "Custom",
    "Métriques affichées": "Displayed metrics",
    "Grille mode personnalisé": "Custom mode grid",
    "Colonnes": "Columns",
    "Rangs": "Rows",
    "(vide)": "(empty)",
    "Sur 2 colonnes": "Span 2 columns",
    "Options des métriques": "Metric options",
    "Général": "General",
    "Langue": "Language",
    "Animations fluides (consomme plus de CPU)":
        "Smooth animations (uses more CPU)",
    "Lancer au démarrage": "Start with Windows",
    "Toujours au premier plan": "Always on top",
    "Icône dans la zone de notification": "Icon in the notification area",
    "Ouvrir le dossier des journaux": "Open the log folder",
    "À savoir": "Good to know",
    # Metrics
    "Réseau": "Network",
    "Réseau réception": "Network download",
    "Réseau envoi": "Network upload",
    "Réception": "Download",
    "Envoi": "Upload",
    "Réception et envoi": "Download and upload",
    "Pourcentage": "Percentage",
    "Pourcentage et valeur": "Percentage and value",
    "Valeur": "Value",
    "Temp. GPU": "GPU temp",
    "FPS": "FPS",
    "FPS bureau": "Desktop FPS",
    "Windows ne donne les FPS des jeux qu'aux comptes du groupe "
    "« Utilisateurs du journal de performances ». Ajoutez-y votre "
    "compte, puis fermez votre session Windows et rouvrez-la. En "
    "attendant, ce sont les FPS du bureau qui s'affichent.":
        "Windows only gives the FPS of games to the accounts of the "
        "\"Performance Log Users\" group. Add your account to it, then sign "
        "out of Windows and back in. Until then, the desktop FPS is shown.",
    "Ajouter mon compte au groupe": "Add my account to the group",
    # Units
    "o": "B",
    "Ko": "KB",
    "Mo": "MB",
    "Go": "GB",
    "To": "TB",
}

_language = DEFAULT


def codes():
    return [code for code, _name in LANGUAGES]


def language():
    return _language


def set_language(code):
    """Switch every text to that language, the default one if unknown."""
    global _language
    _language = code if code in codes() else DEFAULT


def tr(text):
    """The French `text` in the current language."""
    if _language == "fr":
        return text
    return ENGLISH.get(text, text)


def decimal_mark():
    return "," if _language == "fr" else "."
