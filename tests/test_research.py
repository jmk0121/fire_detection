from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.services.research_algorithms import flashover_proxy, pdr, structural_anomaly, structural_limits, trilaterate


class AlgorithmTests(unittest.TestCase):
    def test_fire_forecast_does_not_read_future(self):
        t = np.arange(0., 181., 5.)
        temperature = 20 + 3*t
        prefix = flashover_proxy(t[:21], temperature[:21])
        full = flashover_proxy(t, temperature)
        np.testing.assert_allclose(prefix['predicted_c'], full['predicted_c'][:21], equal_nan=True)
        self.assertAlmostEqual(full['predicted_c'][20], 500.)
        self.assertEqual(full['state'][28], 'watch')

    def test_missing_temperature_is_unknown_and_not_filled(self):
        t = np.arange(0., 181., 5.)
        temperature = np.full(len(t), 100.)
        temperature[20] = np.nan
        result = flashover_proxy(t, temperature)
        self.assertEqual(result['state'][20], 'unknown')
        self.assertEqual(result['state'][21], 'unknown')
        self.assertEqual(result['state'][-1], 'below')
        with self.assertRaises(ValueError): flashover_proxy([0, 5, 5], [1, 2, 3])

    def test_structure_needs_both_signals_and_sustained_evidence(self):
        t = np.arange(181.)
        limits = structural_limits(t, np.zeros_like(t))
        displacement = np.where(t < 100, 0., (t-100)*.5)
        result = structural_anomaly(t, displacement, limits)
        self.assertNotEqual(result['state'][106], 'anomaly')
        self.assertEqual(result['state'][125], 'anomaly')
        prefix = structural_anomaly(t[:130], displacement[:130], limits)
        self.assertEqual(prefix['state'], result['state'][:130])
        np.testing.assert_allclose(prefix['rate_mm_min'], result['rate_mm_min'][:130], equal_nan=True)
        displacement[140] = np.nan
        result = structural_anomaly(t, displacement, limits)
        self.assertEqual(result['state'][140], 'unknown')

    def test_imu_static_bias_and_causality(self):
        t = np.arange(0., 70., .01)
        acceleration = np.tile([0., 0., 9.81], (len(t), 1))
        gyro = np.full(len(t), .01)
        stationary = pdr(t, acceleration, gyro)
        self.assertEqual(len(stationary['steps']), 0)
        np.testing.assert_allclose(stationary['xy'], 0.)
        acceleration[:, 2] += np.where(t >= 40, 3*np.sin(2*np.pi*2*(t-40)), 0.)
        full = pdr(t, acceleration, gyro)
        prefix = pdr(t[:5500], acceleration[:5500], gyro[:5500])
        self.assertGreater(len(prefix['steps']), 20)
        np.testing.assert_allclose(prefix['xy'], full['xy'][:5500])
        gyro[6000] = np.nan
        with self.assertRaises(ValueError): pdr(t, acceleration, gyro)

    def test_uwb_geometry_and_invalid_anchors(self):
        anchors = np.array([[0., 0.], [10., 0.], [0., 10.], [10., 10.]])
        ranges = np.linalg.norm(anchors - [3., 4.], axis=1)
        result = trilaterate(anchors, ranges)
        self.assertAlmostEqual(result['x'], 3.)
        self.assertAlmostEqual(result['y'], 4.)
        self.assertLess(result['residual_m'], 1e-10)
        with self.assertRaises(ValueError): trilaterate([[0, 0], [1, 0], [2, 0]], [1, 2, 3])
        with self.assertRaises(ValueError): trilaterate(anchors, [-1, 2, 3, 4])


class ResearchAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.client = TestClient(app)

    def test_replay_artifacts_and_metrics_are_finite_and_consistent(self):
        catalog = self.client.get('/api/v1/research/catalog')
        self.assertEqual(catalog.status_code, 200)
        experiments = catalog.json()['experiments']
        self.assertEqual(len(experiments), 10)
        for meta in experiments:
            response = self.client.get(f"/api/v1/research/experiments/{meta['id']}")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.text, parse_constant=lambda x: self.fail(f'Invalid number {x}'))
            self.assertGreater(len(data['points']), 50)
            self.assertTrue(all(a['t'] < b['t'] for a, b in zip(data['points'], data['points'][1:])))
            csv = self.client.get(f"/api/v1/research/experiments/{meta['id']}/csv")
            self.assertEqual(csv.status_code, 200)
            self.assertIn('attachment', csv.headers['content-disposition'])
        fire4 = self.client.get('/api/v1/research/experiments/flash-4').json()
        self.assertEqual(fire4['metrics']['first_600_s'], 3480.)
        self.assertEqual(fire4['metrics']['lead_s'], 30.)

    def test_unknown_ids_missing_data_and_uwb_validation(self):
        self.assertEqual(self.client.get('/api/v1/research/experiments/no-such-id').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/research/sources/no-such-id').status_code, 404)
        with tempfile.TemporaryDirectory() as folder, patch('app.research_api.DATA', Path(folder)):
            self.assertEqual(self.client.get('/api/v1/research/catalog').status_code, 503)
        bad = self.client.post('/api/v1/research/uwb', json={'anchors': [[0, 0], [1, 0], [2, 0]], 'ranges': [1, 2, 3]})
        self.assertEqual(bad.status_code, 422)

    def test_research_page_and_assets(self):
        self.assertIn('안전 연구실', self.client.get('/research').text)
        self.assertIn('/research', self.client.get('/').text)
        for asset in ['research.js', 'research.css']:
            self.assertEqual(self.client.get('/static/' + asset).status_code, 200)


if __name__ == '__main__': unittest.main()
