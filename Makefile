run:
	if [ ! -d ".venv" ]; then \
		make-venv; \
	fi
	. ./.venv/bin/activate && uvicorn app.main:app --reload

make-venv:
	# if .venv directory does not exist, create it
	if [ ! -d ".venv" ]; then \
		python3 -m venv .venv; \
	fi
	# install dependencies
	. ./.venv/bin/activate && pip install -r requirements.txt

decrypt-env:
	@echo "Decrypting environment variables..."
	@gpg --quiet --batch --yes --decrypt --output .env .env.gpg

encrypt-env:
	@echo "Encrypting environment variables..."
	@gpg --quiet --batch --yes --symmetric --cipher-algo AES256 --output .env.gpg .env