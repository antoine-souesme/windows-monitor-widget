---
name: release
description: Use when the user asks to release Monitor Widget, publish a new version, ship a new installer, or bump the version number of this project
---

# Release Monitor Widget

Publie une nouvelle version du widget en passant par `main`, puis remet
`develop` à jour. Le tag poussé déclenche la construction de
le paquet `.msix` sur GitHub Actions et l'attache à la release.

## Version

La version est fournie en argument (par exemple `1.2.0`). Si elle est absente,
la demander à l'utilisateur et ne rien faire tant qu'elle n'est pas connue.
Format attendu : `X.Y.Z`, sans préfixe `v`.

## Avant de commencer

Refuser et prévenir l'utilisateur si l'une de ces conditions est vraie :

- l'arbre de travail n'est pas propre (`git status --porcelain` renvoie du texte)
- la version demandée n'est pas supérieure à celle de `monitor_widget/version.py`
- le tag `vX.Y.Z` existe déjà (`git tag -l` et `git ls-remote --tags origin`)
- `python -m compileall -q main.py monitor_widget` échoue
- `python -c "import monitor_widget.config, monitor_widget.probes, monitor_widget.system"`
  échoue (dépendances manquantes : prévenir plutôt que d'installer quoi que ce soit)

## Étapes

1. `git fetch` puis `git checkout develop && git pull`
2. `git checkout main && git pull`
3. `git merge develop --no-ff -m "Fusion de develop pour la version X.Y.Z"`
4. Remplacer `__version__` dans `monitor_widget/version.py` par `X.Y.Z`
5. `git add monitor_widget/version.py && git commit -m "Version X.Y.Z"`
6. `git tag vX.Y.Z` sur le commit de version
7. `git push origin main --follow-tags`
8. `git checkout develop && git merge main --no-ff -m "Retour de la version X.Y.Z"`
9. `git push origin develop`

Si une fusion tombe en conflit, s'arrêter et prévenir l'utilisateur : ne jamais
résoudre un conflit de fusion de release tout seul.

Le numéro de version ne vit qu'à un seul endroit : ne pas le recopier dans
le manifeste MSIX, le spec PyInstaller ou le workflow, qui le lisent déjà.

## À la fin

Annoncer la version publiée et l'état des deux branches, en une ou deux
phrases, puis donner le lien du workflow de release en cours
(`gh run list --workflow msix.yml --limit 1`). Le paquet `.msix` apparaît
dans la release GitHub quelques minutes plus tard.

Si le workflow échoue, le signaler mais ne rien retenter sans l'accord de
l'utilisateur : le tag est déjà poussé, seule la construction est à reprendre.

## Hors périmètre

Pas de création manuelle de la release GitHub ni d'envoi du paquet à la
main (le workflow s'en charge), pas de pull request, pas de signature de code :
uniquement les fusions, le tag et les poussées décrits ci-dessus.
