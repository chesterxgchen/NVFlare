#!/bin/bash

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
    gcc -c encryption_linux.c -o encryption.o
fi 