// import express from "express";
// import type { Request, Response } from "express";
// import { paymentMiddleware } from "x402-express";
// import { Buffer } from "buffer";
// import dotenv from "dotenv";
export {};
// dotenv.config();
// const RECIPIENT_ADDRESS = process.env.RECIPIENT_ADDRESS
// const PORT: number = Number(process.env.DEMO_SERVER_PORT) || 7021;
// const app = express();
// app.use(express.json());
// // Helper to decode Base64 → JSON
// function decodeBase64Json(base64Str: string): any | null {
//   try {
//     const jsonStr = Buffer.from(base64Str, "base64").toString("utf-8");
//     return JSON.parse(jsonStr);
//   } catch (err) {
//     console.error("Failed to decode Base64 x-payment header:", err);
//     return null;
//   }
// }
// app.use(
//   paymentMiddleware(
//     "0x55D84680053B999fa3c452D82c5b2743B3AdD424", // receiver wallet
//     {
//       "GET /payments": {
//         price: "$1.00",
//         network: "base-sepolia",
//       },
//     },
//     {
//       url: "https://x402.org/facilitator",
//     },
//   ),
// );
// // Health check endpoint
// app.get("/health", (req, res) => {
//   res.status(200).json({ status: "ok", message: "Server is running" });
// });
// app.get("/", (req: Request, res: Response) => {
//   res.send(`Welcome to the X402 Payments Server!<br>`)
// });
// // Protected route
// app.post("/payments", (req: Request, res: Response) => {
//   const rawHeader = req.headers["x-payment"];
//   console.log("=== Raw X-PAYMENT header ===\n", rawHeader);
//   const decoded = typeof rawHeader === "string"
//     ? decodeBase64Json(rawHeader)
//     : null;
//   console.log("=== Decoded X-PAYMENT ===\n", JSON.stringify(decoded, null, 2));
//   if (decoded) {
//     console.log("Full payload:", JSON.stringify(decoded.payload, null, 2));
//   }
//   const data = req.body;
//   const amount = data["amount"];
//   res.send({
//     data: {
//       message: "Payment received successfully",
//       amount: amount,
//       id: 1234
//     },
//   });
// });
// app.listen(PORT, "0.0.0.0", () => {
//   console.log(`Server listening at http://localhost:${PORT}/`);
// });
//# sourceMappingURL=server.js.map