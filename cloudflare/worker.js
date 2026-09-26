/**
 * Puerta de entrada de Cloudin en Cloudflare.
 *
 * Cloudflare Pages y los Workers no ejecutan Django: Django corre dentro de un
 * contenedor (Cloudflare Containers, imagen del Dockerfile de la raíz). Este Worker
 * recibe cada petición en el borde de Cloudflare y se la pasa a ese contenedor.
 *
 * Hay UN solo contenedor ("principal") para todos los restaurantes: la caché de
 * Django (topes de intentos, llaves anti-duplicado de los pedidos, token de Factus)
 * vive en la memoria de ese proceso y debe ser una sola.
 *
 * Guía completa: DESPLIEGUE-CLOUDFLARE.md
 */

import { Container, getContainer } from "@cloudflare/containers";
import { env as entorno } from "cloudflare:workers";

// El primer arranque crea las tablas en Postgres y puede tardar bastante más que
// los 20 s que la librería espera por defecto a que Django abra el puerto.
const ESPERA_ARRANQUE_MS = 180_000;

/** Variables y secretos del Worker que son texto: son la configuración de Django. */
function variablesDeDjango() {
	return Object.fromEntries(Object.entries(entorno).filter(([, valor]) => typeof valor === "string"));
}

export class ContenedorCloudin extends Container {
	defaultPort = 8000;
	// Sin peticiones durante este tiempo el contenedor se apaga (y deja de cobrar).
	// La siguiente visita lo vuelve a encender: unos segundos de espera.
	sleepAfter = "15m";
	// Chequeo de salud: la ruta pública que no necesita restaurante.
	pingEndpoint = "localhost/api/v1/ping/";
	envVars = variablesDeDjango();

	async fetch(request) {
		const { status } = await this.getState();
		if (status !== "healthy" || !this.ctx.container.running) {
			const origen = new URL(request.url).origin;
			await this.startAndWaitForPorts({
				startOptions: {
					envVars: {
						...this.envVars,
						// Enlaces absolutos (invitaciones, enlace del panel). Si no se configuró,
						// la dirección por la que llegó la visita (p. ej. cloudin.<cuenta>.workers.dev).
						CLOUDIN_PUBLIC_URL: this.envVars.CLOUDIN_PUBLIC_URL || origen,
					},
				},
				cancellationOptions: { portReadyTimeoutMS: ESPERA_ARRANQUE_MS, abort: request.signal },
			});
		}
		return this.containerFetch(request, this.defaultPort);
	}
}

export default {
	async fetch(request, env) {
		const url = new URL(request.url);
		const cabeceras = new Headers(request.headers);

		// Django confía en estas dos cabeceras (SECURE_PROXY_SSL_HEADER e ip_de()), así
		// que las escribe el Worker y nunca se aceptan como las mande el navegador:
		// - el contenedor recibe HTTP plano; esto le dice que la visita llegó por HTTPS.
		cabeceras.set("X-Forwarded-Proto", url.protocol.replace(":", ""));
		// - la IP real del cliente, para los topes de intentos por IP.
		const ip = request.headers.get("CF-Connecting-IP");
		if (ip) {
			cabeceras.set("X-Forwarded-For", ip);
		} else {
			cabeceras.delete("X-Forwarded-For");
		}

		// redirect: "manual" — las redirecciones de Django (p. ej. al login) llegan tal
		// cual al navegador en vez de seguirse dentro de Cloudflare.
		const peticion = new Request(request, { headers: cabeceras, redirect: "manual" });
		return getContainer(env.CLOUDIN, "principal").fetch(peticion);
	},
};
