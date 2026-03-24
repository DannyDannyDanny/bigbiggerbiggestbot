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
        ]);

        localtunnel = pkgs.buildNpmPackage {
          pname = "localtunnel";
          version = "2.0.2";
          src = pkgs.fetchFromGitHub {
            owner = "localtunnel";
            repo = "localtunnel";
            rev = "v2.0.2";
            hash = "sha256-6gEK1VjF25Kbe2drxbxUKDNJGqZ+OXgkulPkAkMR2+k=";
          };
          npmDepsHash = "sha256-R9FYkEe93oGF+dR7i1MxwzEW3EM3SasH/B6LLC2CNXM=";
          dontNpmBuild = true;
        };
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [ pythonEnv localtunnel ];
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
            export PATH="${pkgs.lib.makeBinPath [ pythonEnv localtunnel ]}:$PATH"
            exec ${pythonEnv}/bin/python "$PWD/start.py"
          '');
        };
      }
    );
}
