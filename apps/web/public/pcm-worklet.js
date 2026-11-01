// Runs on the audio thread: averages the mic down to 16 kHz mono and posts 16-bit PCM about every 250 ms.
class Pcm16k extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.t = 0; this.sum = 0; this.n = 0; this.out = [];
    this.port.onmessage = () => this.flush(); // sent right before the recording stops
  }
  flush() {
    if (!this.out.length) return;
    const buf = Int16Array.from(this.out);
    this.port.postMessage(buf.buffer, [buf.buffer]);
    this.out = [];
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this.sum += ch[i]; this.n++; this.t += 1;
      if (this.t >= this.ratio) {
        this.t -= this.ratio;
        const v = Math.max(-1, Math.min(1, this.sum / this.n));
        this.out.push(v < 0 ? v * 32768 : v * 32767);
        this.sum = 0; this.n = 0;
      }
    }
    if (this.out.length >= 4000) this.flush();
    return true;
  }
}
registerProcessor("pcm16k", Pcm16k);
