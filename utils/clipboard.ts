export async function copyToClipboard(text: string): Promise<void> {
	if (typeof navigator !== "undefined" && navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
		try {
			await navigator.clipboard.writeText(text);
			return;
		} catch (error) {
			// fall through to execCommand fallback
		}
	}
	fallbackCopy(text);
}

function fallbackCopy(text: string): void {
	if (typeof document === "undefined") {
		throw new Error("Clipboard is unavailable in this environment.");
	}
	const textarea = document.createElement("textarea");
	textarea.value = text;
	textarea.setAttribute("readonly", "true");
	textarea.style.position = "fixed";
	textarea.style.top = "-9999px";
	textarea.style.opacity = "0";
	document.body.appendChild(textarea);
	textarea.select();
	try {
		const successful = document.execCommand("copy");
		if (!successful) {
			throw new Error("execCommand copy failed");
		}
	} finally {
		document.body.removeChild(textarea);
	}
}
