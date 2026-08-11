# Disable the frozen modules flag to allow the nbconvert to work
$Env:PYDEVD_DISABLE_FILE_VALIDATION=1

Push-Location .\0-Pre-requisites
jupyter nbconvert --to notebook --execute --inplace 1-Git.ipynb;
jupyter nbconvert --to notebook --execute --inplace 2-Docker.ipynb;
Pop-Location
