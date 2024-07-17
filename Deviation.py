import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
import os
import json
import base64

def detect_dots(image):
    """Detect dots in the image using blob detection with sub-pixel accuracy."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Blob detection parameters
    params = cv2.SimpleBlobDetector_Params()
    params.filterByArea = True
    params.minArea = 50
    params.maxArea = 5000
    params.filterByCircularity = True
    params.minCircularity = 0.7
    params.filterByConvexity = True
    params.minConvexity = 0.8
    params.filterByInertia = True
    params.minInertiaRatio = 0.5

    detector = cv2.SimpleBlobDetector_create(params)
    keypoints = detector.detect(gray)

    if not keypoints:
        return np.array([])
    # Refine the coordinates using sub-pixel accuracy
    points = np.array([kp.pt for kp in keypoints], dtype=np.float32)
    refined_points = cv2.cornerSubPix(gray, points, (5, 5), (-1, -1), 
                                      criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.1))
    return refined_points

def match_dots(dots_image1, dots_image2):
    """Match dots using the Hungarian method with a flexible cost matrix."""
    cost_matrix = np.array([[np.linalg.norm(dot1 - dot2) for dot2 in dots_image2] for dot1 in dots_image1])
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    matched_pairs_ref = [dots_image1[i] for i in row_ind]
    matched_pairs_test = [dots_image2[j] for j in col_ind]
    
    return matched_pairs_ref, matched_pairs_test

def calculate_deviation(dot1, dot2):
    """Calculate the deviation between two dots."""
    return np.linalg.norm(dot1 - dot2)

def visualize_results(image1, image2, matched_pairs_ref, matched_pairs_test, filename=None):
    """Draw dots and connecting lines on the images for visualization."""
    for dot1, dot2 in zip(matched_pairs_ref, matched_pairs_test):
        cv2.circle(image1, tuple(map(int, dot1)), 3, (0, 0, 255), -1)
        cv2.circle(image2, tuple(map(int, dot2)), 3, (0, 255, 0), -1)
        cv2.line(image1, tuple(map(int, dot1)), tuple(map(int, dot2)), (255, 0, 0), 1)

    combined_image = np.hstack((image1, image2))
    
    return combined_image

def filter_outliers(deviations):
    """Filter out outliers from the list of deviations."""
    Q1 = np.percentile(deviations, 25)
    Q3 = np.percentile(deviations, 75)
    IQR = Q3 - Q1
    lower_bound = Q1 - 1.5 * IQR
    upper_bound = Q3 + 1.5 * IQR

    filtered_deviations = [deviation for deviation in deviations if lower_bound <= deviation <= upper_bound]
    return filtered_deviations

def calculate_average(deviations):
    if not deviations:
        return 0
    deviation_sum = sum(deviations)
    average_deviation = deviation_sum / len(deviations)
    return average_deviation

def pixels_to_arcmin(deviation_pixels, angular_resolution_deg_per_pixel):
    deviation_arcmin = deviation_pixels * angular_resolution_deg_per_pixel * 60
    return deviation_arcmin

def main(image1, image2, angular_resolution):
    dots_image1 = detect_dots(image1)
    dots_image2 = detect_dots(image2)


    if len(dots_image1) == 0 or len(dots_image2) == 0:
        return "No dots detected", cv2.hconcat([image1, image2])
    
    matched_pairs_ref, matched_pairs_test = match_dots(dots_image1, dots_image2)

    # Calculate the deviation between corresponding dots
    deviations = [calculate_deviation(dot1, dot2) for dot1, dot2 in zip(matched_pairs_ref, matched_pairs_test)]
    filtered_deviations = filter_outliers(deviations)

    if not filtered_deviations:
        return "No valid deviations calculated", cv2.hconcat([image1, image2])

    deviation_pixels = calculate_average(filtered_deviations) 
    angular_resolution_deg_per_pixel = angular_resolution 
    deviation_arcmin = pixels_to_arcmin(deviation_pixels, angular_resolution_deg_per_pixel)
    combined_image = visualize_results(image1.copy(), image2.copy(), matched_pairs_ref, matched_pairs_test, filename="visualization_result.jpg")

    return deviation_arcmin, combined_image

def base64_to_cv2(base64_string):
    img_data = base64.b64decode(base64_string)
    nparr = np.frombuffer(img_data, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

def cv2_to_base64(image):
    _, buffer = cv2.imencode('.jpg', image)
    return base64.b64encode(buffer).decode('utf-8')


def process_captured_images():
    with open('form_data.json', 'r') as f:
        data = json.load(f)

    if len(data['captured_images']) < 2:
        return {"error": "Not enough images captured"}

    reference_image = base64_to_cv2(data['captured_images'][0])
    results = []

    for i, test_image_base64 in enumerate(data['captured_images'][1:], 1):
        test_image = base64_to_cv2(test_image_base64)
        
        angular_resolution = 0.1  # Example value, adjust as needed
        
        deviation, combined_image = main(reference_image, test_image, angular_resolution)
        
        combined_image_base64 = cv2_to_base64(combined_image)

        
        results.append({
            f"capture_{i}": {
                "deviation": str(deviation),
                "combined_image": combined_image_base64
            }
        })

    if 'captured_images' in data:
        del data['captured_images']

    data.update({"results": results})

    with open('form_data.json', 'w') as f:
        json.dump(data, f)

    return data

if __name__ == "__main__":
    process_captured_images()