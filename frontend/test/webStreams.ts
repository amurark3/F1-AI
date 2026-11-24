import * as webStreams from "node:stream/web";

// pool "vmThreads" gives jsdom a VM context without Node's web-stream globals,
// which MSW needs; this runs before test/setup.ts imports MSW.
for (const [name, value] of Object.entries(webStreams)) {
  if (!(name in globalThis)) Object.assign(globalThis, { [name]: value });
}
