{
  description = "Telegram Fitness Bot — Mini App for tracking gym workouts";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        python = pkgs.python3;

        pythonEnv = python.withPackages (ps: with ps; [
          python-telegram-bot
          aiohttp
        ]);

        # localtunnel via npm
        localtunnel = pkgs.buildNpmPackage {
          pname = "localtunnel";
          version = "2.0.2";
          src = pkgs.fetchFromGitHub {
            owner = "localtunnel";
            repo = "localtunnel";
            rev = "v2.0.2";
            hash = "sha256-deKDwCjGT+0YjeW/AM2J6IH+hEoQrESmKKM23n0JLWY=";
          };
          npmDepsHash = "sha256-R9FYkEe93oGF+dR7i1MxwzEW3EM3SasH/B6LLC2CNXM=";
          dontNpmBuild = true;
        };

        runtimePath = pkgs.lib.makeBinPath [
          pythonEnv
          localtunnel
        ];

      in {
        packages.default = pkgs.stdenv.mkDerivation {
          pname = "telegram-fitness-bot";
          version = "0.1.0";

          src = pkgs.lib.cleanSource ./.;

          nativeBuildInputs = [ pkgs.makeWrapper ];

          installPhase = ''
            mkdir -p $out/lib/telegram-fitness-bot
            cp -r start.py bot.py server.py database.py config.py webapp $out/lib/telegram-fitness-bot/

            mkdir -p $out/bin

            # Main entry point: `nix run` → start.py
            makeWrapper ${pythonEnv}/bin/python $out/bin/telegram-fitness-bot \
              --prefix PATH : ${runtimePath} \
              --add-flags "$out/lib/telegram-fitness-bot/start.py"
          '';

          meta = with pkgs.lib; {
            description = "Telegram Mini App for tracking gym workouts";
            license = licenses.mit;
            mainProgram = "telegram-fitness-bot";
          };
        };

        # `nix develop` — interactive dev shell
        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
            localtunnel
          ];

          shellHook = ''
            echo ""
            echo "  Fitness Bot dev shell"
            echo "  python: $(python --version)"
            echo "  lt:     $(lt --version)"
            echo ""
            echo "  Run:  python start.py"
            echo ""
          '';
        };
      }
    );
}
