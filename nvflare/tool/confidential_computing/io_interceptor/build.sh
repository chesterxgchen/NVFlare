#!/bin/bash

# Find OpenSSL installation
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux - try pkg-config first
    if pkg-config openssl; then
        export CFLAGS="$(pkg-config --cflags openssl)"
        export LDFLAGS="$(pkg-config --libs openssl)"
    else
        # Fallback paths
        export CFLAGS="-I/usr/include/openssl"
        export LDFLAGS="-L/usr/lib -lssl -lcrypto"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    # Mac OS X - use brew paths
    if [ -d "/usr/local/opt/openssl" ]; then
        export CFLAGS="-I/usr/local/opt/openssl/include"
        export LDFLAGS="-L/usr/local/opt/openssl/lib -lssl -lcrypto"
    fi
fi

# Check OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    # Mac OS X
    brew install openssl
    export OPENSSL_ROOT_DIR=$(brew --prefix openssl)
    export OPENSSL_INCLUDE_DIR=$OPENSSL_ROOT_DIR/include
    export OPENSSL_CRYPTO_LIBRARY=$OPENSSL_ROOT_DIR/lib/libcrypto.dylib
    export OPENSSL_SSL_LIBRARY=$OPENSSL_ROOT_DIR/lib/libssl.dylib
else
    # Linux
    sudo apt-get install libssl-dev
fi

if [[ "$OSTYPE" == "darwin"* ]]; then
    # Mac OS X build
    gcc -c encryption_darwin.c -o encryption.o
else
    # Linux build
    gcc $CFLAGS -c encryption_linux.c -o encryption.o $LDFLAGS
fi 