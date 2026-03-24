{
  description = "BigBiggerBiggestBot — Telegram fitness tracker";

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
        ]);
      in
      {
        # `nix develop` — drop into a shell with everything available
        devShells.default = pkgs.mkShell {
          packages = [ pythonEnv ];
          shellHook = ''
            echo "💪 BigBiggerBiggestBot dev shell"
            echo "   Run:  python bot.py"
          '';
        };

        # `nix run` — start the bot from the current directory
        apps.default = {
          type = "app";
          program = toString (pkgs.writeShellScript "run-bot" ''
            exec ${pythonEnv}/bin/python "$PWD/bot.py"
          '');
        };
      }
    );
}
