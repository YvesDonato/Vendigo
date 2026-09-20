"""Remove generated speech's quiet padding without deleting pauses inside a sentence."""

from vendi.speech.turn import pcm_rms


async def trim_speech(source, rate=24000):
    frame_bytes = rate // 50 * 2  # 20 ms of mono PCM
    padding_bytes = rate // 10 * 2  # Retain 100 ms for soft initial/final consonants.
    pending = bytearray()
    quiet = bytearray()
    started = False

    def frame(data):
        nonlocal started
        if pcm_rms(data) >= 120:
            prefix = bytes(quiet if started else quiet[-padding_bytes:])
            quiet.clear()
            started = True
            return prefix + data
        quiet.extend(data)
        if not started and len(quiet) > padding_bytes:
            del quiet[:-padding_bytes]
        return b""

    try:
        async for data in source:
            pending.extend(data)
            output = bytearray()
            while len(pending) >= frame_bytes:
                data = bytes(pending[:frame_bytes])
                del pending[:frame_bytes]
                output.extend(frame(data))
            if output:
                yield bytes(output)
        if pending:
            output = frame(bytes(pending))
            if output:
                yield output
        if started and quiet:
            yield bytes(quiet[:padding_bytes])
    finally:
        await source.aclose()
