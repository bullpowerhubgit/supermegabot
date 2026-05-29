#!/bin/bash
set -e

GCLOUD_DIR="$HOME/google-cloud-sdk"

# Alte Installation entfernen
if [ -d "$GCLOUD_DIR" ]; then
    rm -rf "$GCLOUD_DIR"
fi

echo "Installing Google Cloud SDK..."

# Download with retry
for i in 1 2 3; do
    echo "Download attempt $i..."
    if curl -fsSL --max-time 300 https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-darwin-arm64.tar.gz -o /tmp/google-cloud-sdk.tar.gz; then
        break
    fi
    echo "Download failed, retrying..."
    sleep 10
done

# Extract
tar -xzf /tmp/google-cloud-sdk.tar.gz -C "$HOME"
rm /tmp/google-cloud-sdk.tar.gz

# Initialize - disable analytics, quiet mode
"$GCLOUD_DIR/install.sh" --quiet --path-update=true --command-completion=false --usage-reporting=false

# Add to PATH for current session
export PATH="$GCLOUD_DIR/bin:$PATH"

# Source shell config
if [ -f "$HOME/.zshrc" ]; then
    echo 'export PATH="$HOME/google-cloud-sdk/bin:$PATH"' >> "$HOME/.zshrc"
fi

echo "Google Cloud SDK installed successfully!"
echo "Run 'source ~/.zshrc' or restart terminal to use gcloud."
