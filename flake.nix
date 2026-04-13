{
  description = "BigBiggerBiggestBot — Telegram fitness tracker with Mini App";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        python = pkgs.python3;

        pythonEnv = python.withPackages (ps: with ps; [
          python-telegram-bot
          python-dotenv
          aiohttp
          pytest
          pytest-asyncio
        ]);

      in
      {
        devShells.default = pkgs.mkShell {
          packages = [ pythonEnv pkgs.cloudflared ];
          shellHook = ''
            echo "💪 BigBiggerBiggestBot dev shell"
            echo "   Run:  python start.py    (server + tunnel + bot)"
            echo "   Run:  python bot.py       (bot only, no mini app)"
          '';
        };

        # `nix run` — start everything via start.py
        apps.default = {
          type = "app";
          program = toString (pkgs.writeShellScript "run-fitness-bot" ''
            export PATH="${pkgs.lib.makeBinPath [ pythonEnv pkgs.cloudflared ]}:$PATH"
            exec ${pythonEnv}/bin/python "$PWD/start.py"
          '');
        };
      }
    );
}
