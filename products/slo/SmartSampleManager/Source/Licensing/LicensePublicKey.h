#pragma once

// ============================================================================
// DEV / TEST KEY -- generated locally by licensing_server/generate_keypair.py
// for exercising the activation flow against the local mock server. This is
// NOT a production secret (it's a public key, so it's not secret at all --
// what matters is that the PRIVATE half never ships anywhere near the
// client). Before shipping a real build, generate a separate production
// keypair on the real licensing backend and swap the constant below for that
// environment's public key. Never let the private key touch this repo.
// ============================================================================
namespace Licensing {
    constexpr const char* kServerPublicKeyBase64 = "/l2APWYxLuAwLa7Xm+y8LJPQcrJ/1+SlrTTJTrDzpFU=";
}
