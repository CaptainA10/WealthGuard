#!/usr/bin/env bash
# One-time Azure setup for the quality-engine deployment (cahier des charges
# Phase 9). Run this ONCE in Azure Cloud Shell (portal.azure.com -> the ">_"
# icon top right) -- it needs no local install, `az` is already available
# there, and it never sees or stores a long-lived secret: GitHub Actions
# authenticates via OpenID Connect (a federated credential), not a client
# secret.
#
# What it creates, all inside one resource group so it is easy to review or
# delete entirely later:
#   - An Azure AD app registration + federated credential, scoped to this
#     exact repo and the `main` branch only (no other repo or branch can use
#     it).
#   - "Contributor" role for that identity, scoped to the resource group only
#     -- not the whole subscription.
#   - An App Service Plan on the F1 tier (Azure's free tier: no cost, ever,
#     independent of the trial credit) and a Linux Web App running Java 17.
#   - CORS allow-listing the GitHub Pages origin so the deployed frontend can
#     call this engine directly from the browser (see quality-engine's
#     WebConfig).
#
# After running, copy the three printed values into
# GitHub -> Settings -> Secrets and variables -> Actions -> New repository
# secret, then tell Claude the WEBAPP_NAME you ended up with (it must be
# globally unique across all of Azure; the script picks a default and tells
# you if it had to fall back to something else).

set -euo pipefail

RESOURCE_GROUP="wealthguard-rg"
LOCATION="francecentral"
OWNER="CaptainA10"
REPO_NAME="WealthGuard"
APP_REG_NAME="wealthguard-github-actions"
PLAN_NAME="wealthguard-plan"
WEBAPP_NAME="${WEBAPP_NAME:-wealthguard-quality-engine}"
GH_PAGES_ORIGIN="https://captaina10.github.io"

echo "== Subscription courante =="
az account show --query "{name:name, id:id}" -o table

SUBSCRIPTION_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)

echo "== 1/5 Groupe de ressources =="
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" -o none

echo "== 2/5 Identite pour GitHub Actions (OIDC, sans secret) =="
APP_ID=$(az ad app create --display-name "$APP_REG_NAME" --query appId -o tsv)
az ad sp create --id "$APP_ID" -o none 2>/dev/null || echo "  (service principal deja existant, on continue)"

# GitHub's OIDC "sub" claim includes the numeric owner/repo IDs
# ("repo:OWNER@OWNER_ID/REPO@REPO_ID:ref:...", not just the names) -- derived
# from the public API rather than hardcoded, so this keeps working if the
# repo is ever renamed or transferred.
OWNER_ID=$(curl -s "https://api.github.com/users/$OWNER" | grep -o '"id": *[0-9]*' | head -1 | grep -o '[0-9]*')
REPO_ID=$(curl -s "https://api.github.com/repos/$OWNER/$REPO_NAME" | grep -o '"id": *[0-9]*' | head -1 | grep -o '[0-9]*')
SUBJECT="repo:${OWNER}@${OWNER_ID}/${REPO_NAME}@${REPO_ID}:ref:refs/heads/main"
echo "  subject OIDC attendu : $SUBJECT"

# Delete-then-create rather than a plain create: makes this step idempotent
# even when a credential with the same name already exists but with a
# now-wrong subject (exactly what happened the first time this was run,
# before GitHub's numeric-ID subject format was accounted for).
az ad app federated-credential delete --id "$APP_ID" \
  --federated-credential-id "wealthguard-main-branch" -o none 2>/dev/null || true
az ad app federated-credential create --id "$APP_ID" --parameters '{
  "name": "wealthguard-main-branch",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "'"$SUBJECT"'",
  "audiences": ["api://AzureADTokenExchange"]
}' -o none

echo "== 3/5 Role Contributor, limite a ce groupe de ressources =="
az role assignment create --assignee "$APP_ID" --role Contributor \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP" -o none 2>/dev/null \
  || echo "  (role deja attribue, on continue)"

echo "== 4/5 App Service Plan (F1, gratuit) + Web App (Java 17) =="
az appservice plan create --name "$PLAN_NAME" --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" --sku F1 --is-linux -o none

if ! az webapp create --name "$WEBAPP_NAME" --resource-group "$RESOURCE_GROUP" \
     --plan "$PLAN_NAME" --runtime "JAVA:17-java17" -o none 2>/tmp/webapp_err; then
  echo "  Le runtime string a peut-etre change de syntaxe selon la version d'az. Runtimes Java disponibles :"
  az webapp list-runtimes --os linux --query "[?contains(@, 'java')]" -o table
  echo "  Relance avec : az webapp create --name $WEBAPP_NAME --resource-group $RESOURCE_GROUP --plan $PLAN_NAME --runtime '<runtime-ci-dessus>'"
  cat /tmp/webapp_err
  exit 1
fi

echo "== 5/5 CORS pour le dashboard GitHub Pages =="
az webapp config appsettings set --name "$WEBAPP_NAME" --resource-group "$RESOURCE_GROUP" \
  --settings WEALTHGUARD_CORS_ALLOWED_ORIGINS="$GH_PAGES_ORIGIN" -o none

cat <<EOF

================================================================
 URL du moteur (une fois deploye par la CI) :
   https://$WEBAPP_NAME.azurewebsites.net

 A copier dans GitHub -> Settings -> Secrets and variables -> Actions
 (un secret par ligne) :
   AZURE_CLIENT_ID       = $APP_ID
   AZURE_TENANT_ID       = $TENANT_ID
   AZURE_SUBSCRIPTION_ID = $SUBSCRIPTION_ID

 Nom de la Web App utilise : $WEBAPP_NAME
 (donne ce nom si different de "wealthguard-quality-engine")
================================================================
EOF
